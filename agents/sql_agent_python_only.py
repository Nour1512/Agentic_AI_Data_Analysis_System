import json
import logging
from typing import Any, Dict, List, Union

from agents_schema.common import ErrorInfo, ValidationStatus, WarningInfo
from agents_schema.sql import DataColumn, DataRequest, DataResponse, DataRow
from services.groq_service import GroqService
from database.sqlserver_client import SQLServerClient

# Import system prompts from their separate configuration/prompt files
from prompts.sql_data_request_prompt import DATA_REQUEST_SYSTEM_PROMPT
from prompts.sql_generation_prompt import SQL_GENERATION_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class SQLAgentFromScratch:
    def __init__(
        self,
        groq_service: GroqService,
        database_client: SQLServerClient = None,
        db_service: SQLServerClient = None,
    ):
        self.groq_service = groq_service
        # Support both self.client and self.db_service
        self.db_service = database_client or db_service
        self.client = self.db_service

    def run(self, task_spec: Any, request_id: str) -> DataResponse:
        """Executes the complete SQL generation and execution flow."""
        logger.info(f"SQL Agent started for request_id={request_id}")

        try:
            # 1. Fetch targeted or full database schema
            schema_info = self._retrieve_schema(task_spec)

            # 2. Build DataRequest model with strict normalization
            data_request = self._build_data_request(
                task_spec=task_spec,
                schema_info=schema_info,
                fallback_request_id=request_id,
            )

            # 3. Generate clean T-SQL Query
            sql_query = self._generate_sql(data_request, schema_info)
            logger.info(f"SQL Query generated for request_id={request_id}: {sql_query}")

            # 4. Execute Query against MSSQL Database
            return self._execute_sql(sql_query, request_id)

        except Exception as e:
            logger.error(
                f"SQL Agent run failed for request_id={request_id}: {str(e)}",
                exc_info=True,
            )
            return DataResponse(
                request_id=request_id,
                query_executed="",
                columns=[],
                results=[],
                row_count=0,
                validation_status=ValidationStatus.INVALID,
                warnings=[],
                error=ErrorInfo(message=str(e), code="SQL_AGENT_FAILURE"),
            )

    def _retrieve_schema(self, task_spec: Any) -> str:
        """Retrieves schema for requested tables, or falls back to full schema."""
        tables_required = []
        if isinstance(task_spec, dict):
            tables_required = task_spec.get("tables_required", [])
        elif hasattr(task_spec, "tables_required"):
            tables_required = getattr(task_spec, "tables_required", [])

        if tables_required and hasattr(self.db_service, "get_schema_for_tables"):
            schema = self.db_service.get_schema_for_tables(tables_required)
            if schema:
                return schema

        if hasattr(self.db_service, "get_full_schema"):
            return self.db_service.get_full_schema()
        elif hasattr(self.db_service, "fetch_schema"):
            return self.db_service.fetch_schema()

        return ""

    def _build_data_request(
        self,
        task_spec: Any,
        schema_info: str,
        fallback_request_id: str,
    ) -> DataRequest:
        """Generates LLM JSON output and normalizes it into a DataRequest model."""
        if hasattr(task_spec, "model_dump"):
            task_dict = task_spec.model_dump(mode="json")
        elif isinstance(task_spec, dict):
            task_dict = task_spec
        else:
            task_dict = {"original_question": str(task_spec)}

        user_prompt = f"""
TASK SPECIFICATION:
{json.dumps(task_dict, indent=2, default=str)}

DATABASE SCHEMA:
{schema_info}
"""

        raw_response = self.groq_service.generate(
            system_prompt=DATA_REQUEST_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )

        data = self._parse_json(raw_response)

        # Inject valid request_id into dictionary prior to validation
        data["request_id"] = fallback_request_id

        # --- NORMALIZATION FIXES FOR DataRequest SCHEMA ---

        # 1. Normalize aggregations -> list[str]
        if "aggregations" in data and isinstance(data["aggregations"], list):
            norm_aggs = []
            for item in data["aggregations"]:
                if isinstance(item, dict):
                    agg_type = item.get("type", "SUM").upper()
                    expr = item.get("expression") or item.get("column", "")
                    alias = f" AS {item['alias']}" if "alias" in item else ""
                    norm_aggs.append(f"{agg_type}({expr}){alias}".strip())
                else:
                    norm_aggs.append(str(item))
            data["aggregations"] = norm_aggs

        # 2. Normalize order_by -> list[str]
        if "order_by" in data and isinstance(data["order_by"], list):
            norm_order = []
            for item in data["order_by"]:
                if isinstance(item, dict):
                    expr = item.get("expression") or item.get("column", "")
                    direction = item.get("direction", "ASC").upper()
                    norm_order.append(f"{expr} {direction}".strip())
                else:
                    norm_order.append(str(item))
            data["order_by"] = norm_order

        # 3. Normalize group_by -> list[str]
        if "group_by" in data and isinstance(data["group_by"], list):
            data["group_by"] = [
                item.get("column") if isinstance(item, dict) else str(item)
                for item in data["group_by"]
            ]

        # 4. Normalize columns_required & tables_required -> list[str]
        for field in ["columns_required", "tables_required"]:
            if field in data and isinstance(data[field], list):
                data[field] = [str(x) for x in data[field]]

        return DataRequest.model_validate(data)

    def _generate_sql(self, data_request: DataRequest, schema_info: str) -> str:
        """Generates raw T-SQL query string using LLM."""
        user_prompt = f"""
DATA REQUEST:
{data_request.model_dump_json(indent=2)}

DATABASE SCHEMA:
{schema_info}
"""

        raw_sql = self.groq_service.generate(
            system_prompt=SQL_GENERATION_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )

        return self.clean_sql_query(raw_sql)

    def _execute_sql(self, sql_query: str, request_id: str) -> DataResponse:
        """Executes query and constructs standard DataResponse model safely."""
        try:
            raw_output = self.db_service.execute_query(sql_query)
            logger.info(f"DEBUG RAW OUTPUT: {raw_output}")

            columns_raw = []
            rows_raw = []

            # Match output format from db_service tuple: (rows, columns, metadata)
            if isinstance(raw_output, (list, tuple)):
                if len(raw_output) >= 2:
                    first, second = raw_output[0], raw_output[1]
                    
                    # Detect if index 0 contains actual data rows (dicts with real values)
                    if isinstance(first, list) and len(first) > 0 and isinstance(first[0], dict) and "data_type" not in first[0]:
                        rows_raw = first
                        columns_raw = second
                    # Detect if index 1 contains actual data rows
                    elif isinstance(second, list) and len(second) > 0 and isinstance(second[0], dict) and "data_type" not in second[0]:
                        rows_raw = second
                        columns_raw = first
                    else:
                        rows_raw = first
                        columns_raw = second
                elif len(raw_output) == 1:
                    rows_raw = raw_output[0]

            elif isinstance(raw_output, dict):
                columns_raw = raw_output.get("columns", [])
                rows_raw = raw_output.get("rows", raw_output.get("results", raw_output.get("data", [])))

            columns = []
            col_names = []

            # 1. Parse column headers
            for c in columns_raw:
                if isinstance(c, str):
                    name = c
                elif isinstance(c, dict):
                    name = str(c.get("name") or c.get("column_name") or next(iter(c.values()), "col"))
                elif isinstance(c, (list, tuple)) and len(c) > 0:
                    name = str(c[0])
                else:
                    name = str(c)

                col_names.append(name)
                columns.append(DataColumn(name=name, data_type="str"))

            results = []

            # 2. Extract row values safely (handling Decimals and dicts)
            for row in rows_raw:
                row_dict = {}

                if isinstance(row, dict):
                    # Skip metadata dicts if present
                    if "data_type" in row and "name" in row and len(row) == 2:
                        continue

                    for k, v in row.items():
                        if v is None:
                            row_dict[str(k)] = None
                        elif isinstance(v, (int, float, str, bool)):
                            row_dict[str(k)] = v
                        else:
                            # Convert Decimal, datetime, or custom SQL objects to float/str
                            row_dict[str(k)] = float(v) if hasattr(v, "__float__") else str(v)

                elif hasattr(row, "__getitem__") and not isinstance(row, str):
                    if not col_names:
                        col_names = [f"col_{i}" for i in range(len(row))]
                        columns = [DataColumn(name=cn, data_type="str") for cn in col_names]

                    for idx, col_name in enumerate(col_names):
                        try:
                            val = row[idx]
                        except (IndexError, TypeError):
                            val = None

                        if val is None:
                            row_dict[col_name] = None
                        elif isinstance(val, (int, float, str, bool)):
                            row_dict[col_name] = val
                        else:
                            row_dict[col_name] = float(val) if hasattr(val, "__float__") else str(val)

                if row_dict:
                    results.append(DataRow(values=row_dict))

            logger.info(f"SQL execution successfully built {len(results)} rows for request_id={request_id}: {[r.values for r in results]}")

            return DataResponse(
                request_id=request_id,
                query_executed=sql_query,
                columns=columns,
                results=results,
                row_count=len(results),
                validation_status=(
                    ValidationStatus.VALID if results else ValidationStatus.EMPTY_RESULT
                ),
                warnings=[],
                error=None,
            )
        except Exception as db_err:
            logger.error(
                f"Execution failed for SQL: {sql_query}. Error: {str(db_err)}",
                exc_info=True
            )
            return DataResponse(
                request_id=request_id,
                query_executed=sql_query,
                columns=[],
                results=[],
                row_count=0,
                validation_status=ValidationStatus.INVALID,
                warnings=[],
                error=ErrorInfo(message=str(db_err), code="SQL_EXECUTION_ERROR"),
            )
        
    def _parse_json(self, raw_text: str) -> Dict[str, Any]:
        """Cleans reasoning tags and extracts valid JSON."""
        cleaned = raw_text
        if "<think>" in cleaned and "</think>" in cleaned:
            cleaned = cleaned.split("</think>")[-1].strip()

        if "```json" in cleaned:
            cleaned = cleaned.split("```json")[1].split("```")[0].strip()
        elif "```" in cleaned:
            cleaned = cleaned.split("```")[1].split("```")[0].strip()

        return json.loads(cleaned)

    def clean_sql_query(self, raw_sql: str) -> str:
        """Strips markdown block markers, reasoning tags, and trailing semicolons."""
        cleaned = raw_sql
        if "<think>" in cleaned and "</think>" in cleaned:
            cleaned = cleaned.split("</think>")[-1].strip()

        if "```sql" in cleaned:
            cleaned = cleaned.split("```sql")[1].split("```")[0].strip()
        elif "```" in cleaned:
            cleaned = cleaned.split("```")[1].split("```")[0].strip()

        cleaned = cleaned.strip()

        # Remove trailing semicolon if present to avoid syntax issues during execution
        if cleaned.endswith(";"):
            cleaned = cleaned[:-1].strip()

        return cleaned