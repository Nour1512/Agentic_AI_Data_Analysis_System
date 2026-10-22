import os
import pyodbc
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class SQLServerClient:
    def __init__(self):
        self.host = os.getenv("SQLSERVER_HOST", "localhost")
        self.database = os.getenv("SQLSERVER_DATABASE", "egyptian_ecommerce_dw")
        self.driver = os.getenv("SQLSERVER_DRIVER", "ODBC Driver 18 for SQL Server")
        self.trusted_connection = os.getenv("SQLSERVER_TRUSTED_CONNECTION", "yes")
        
        self.user = os.getenv("SQLSERVER_USER", "")
        self.password = os.getenv("SQLSERVER_PASSWORD", "")
        self.port = os.getenv("SQLSERVER_PORT", "")

    def get_connection(self):
        conn_str = f"DRIVER={{{self.driver}}};SERVER={self.host}"
        if self.port:
            conn_str += f",{self.port}"
        conn_str += f";DATABASE={self.database}"
        
        if self.trusted_connection.lower() == "yes" or self.trusted_connection.lower() == "true":
            conn_str += ";Trusted_Connection=yes"
        else:
            conn_str += f";UID={self.user};PWD={self.password}"
            
        conn_str += ";TrustServerCertificate=yes"
            
        return pyodbc.connect(conn_str)

    def fetch_schema(self, tables_required: list[str] = None) -> str:
        """
        Fetches the schema of the database. If tables_required is provided,
        it only fetches schema for those specific tables.
        """
        schema_info = []
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Get list of tables
                if tables_required and len(tables_required) > 0:
                    format_strings = ','.join(['?'] * len(tables_required))
                    cursor.execute(f"SELECT table_name FROM INFORMATION_SCHEMA.TABLES WHERE table_type = 'BASE TABLE' AND table_name IN ({format_strings})", tables_required)
                else:
                    cursor.execute("SELECT table_name FROM INFORMATION_SCHEMA.TABLES WHERE table_type = 'BASE TABLE'")
                
                tables = [row.table_name for row in cursor.fetchall()]
                
                for table in tables:
                    cursor.execute("SELECT column_name, data_type FROM INFORMATION_SCHEMA.COLUMNS WHERE table_name = ?", (table,))
                    columns = cursor.fetchall()
                    col_details = [f"{col.column_name} ({col.data_type})" for col in columns]
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
                cursor = conn.cursor()
                cursor.execute(query)
                
                if cursor.description is None:
                    conn.commit()
                    return [], [], None
                
                columns_list = [column[0] for column in cursor.description]
                results = []
                
                for row in cursor.fetchall():
                    results.append(dict(zip(columns_list, row)))
                
                columns = []
                for desc in cursor.description:
                    columns.append({
                        "name": desc[0],
                        "data_type": "string"
                    })
                        
                return results, columns, None
        except Exception as e:
            return [], [], str(e)
