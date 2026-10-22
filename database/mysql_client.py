import os
import pymysql
from pymysql.cursors import DictCursor
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class MySQLClient:
    def __init__(self):
        self.host = os.getenv("MYSQL_HOST", "localhost")
        self.user = os.getenv("MYSQL_USER", "root")
        self.password = os.getenv("MYSQL_PASSWORD", "")
        self.database = os.getenv("MYSQL_DATABASE", "")
        self.port = int(os.getenv("MYSQL_PORT", 3306))

    def get_connection(self):
        return pymysql.connect(
            host=self.host,
            user=self.user,
            password=self.password,
            database=self.database,
            port=self.port,
            cursorclass=DictCursor
        )

    def fetch_schema(self, tables_required: list[str] = None) -> str:
        """
        Fetches the schema of the database. If tables_required is provided,
        it only fetches schema for those specific tables.
        """
        schema_info = []
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Get list of tables
                    if tables_required and len(tables_required) > 0:
                        format_strings = ','.join(['%s'] * len(tables_required))
                        cursor.execute(f"SHOW TABLES WHERE `Tables_in_{self.database}` IN ({format_strings})", tuple(tables_required))
                    else:
                        cursor.execute("SHOW TABLES")
                    
                    tables = [list(row.values())[0] for row in cursor.fetchall()]
                    
                    for table in tables:
                        cursor.execute(f"DESCRIBE `{table}`")
                        columns = cursor.fetchall()
                        col_details = [f"{col['Field']} ({col['Type']})" for col in columns]
                        schema_info.append(f"Table: {table}\nColumns: {', '.join(col_details)}")
                        
        except Exception as e:
            return f"Error fetching schema: {str(e)}"
            
        return "\n\n".join(schema_info)

    def execute_query(self, query: str) -> tuple[list[dict], list[dict], str | None]:
        """
        Executes a query and returns (results, columns, error)
        """
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query)
                    results = cursor.fetchall()
                    
                    # Cursor description contains column details: (name, type_code, display_size, internal_size, precision, scale, null_ok)
                    columns = []
                    if cursor.description:
                        for desc in cursor.description:
                            columns.append({
                                "name": desc[0],
                                "data_type": "string" # Simplified mapping, can be enhanced based on type_code
                            })
                            
                    return results, columns, None
        except Exception as e:
            return [], [], str(e)
