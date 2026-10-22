# SQL Agent

The **SQL Agent** is a core component of the Agentic AI Data Analysis System. Its primary responsibility is to translate natural language analytical intents into executable MySQL queries, execute those queries securely, and return structured data responses back to the Orchestrator.

---

## 🏗️ How It Works

The agent is built using **LangGraph**, **LangChain**, and **Groq**. It operates as a state machine with the following nodes in its workflow:

1. **`retrieve_schema` Node:**
   - Connects to the MySQL database via the `MySQLClient` (located in `database/mysql_client.py`).
   - Dynamically extracts the schema (table definitions, columns, and data types) for the required tables specified in the input request.

2. **`generate_sql` Node:**
   - Injects the extracted schema, the user's `query_intent`, and any additional constraints (filters, aggregations, limit, etc.) into a prompt.
   - Calls the **Groq API** (`llama3-70b-8192` by default) to generate a valid raw MySQL query.

3. **`execute_sql` Node:**
   - Executes the generated SQL query against the MySQL database.
   - Extracts the raw results and the column metadata directly from the database cursor.
   - Safely catches any execution errors to prevent the agent from crashing.

4. **`format_response` Node:**
   - Packages the raw execution results into the rigid `DataResponse` Pydantic model (defined in `agents_schema/sql.py`).
   - Assigns standard validation statuses (e.g., `VALID`, `EMPTY_RESULT`, `INVALID`).
   - Returns the finalized payload to the Orchestrator.

---

## 🎯 What It Should Do

- **Accept:** A strictly typed `DataRequest` (containing `request_id`, `query_intent`, `tables_required`, etc.).
- **Process:** Generate and execute valid MySQL dialect SQL.
- **Respond:** Return a strictly typed `DataResponse` (containing `query_executed`, structured `columns`, `results`, `row_count`, and any `error` objects if the query failed).
- **Never Crash:** If the LLM generates bad SQL or the database is unreachable, the agent should catch the exception and return a `DataResponse` with an `error` payload rather than throwing an unhandled exception.

---

## 🧪 How to Test It

We have provided a dedicated test script (`test_sql_agent.py`) in the root directory to help you verify that the agent is fully operational.

### Prerequisites

1. **Install Dependencies:**
   Ensure you have all the required Python packages installed:
   ```bash
   pip install langgraph langchain-groq langchain-core pydantic pymysql python-dotenv
   ```

2. **Environment Variables:**
   Copy the provided `.env.example` file to a new file named `.env` in the root directory. Fill in your credentials:
   ```env
   MYSQL_HOST=localhost
   MYSQL_USER=root
   MYSQL_PASSWORD=your_password
   MYSQL_DATABASE=your_database_name
   MYSQL_PORT=3306
   
   GROQ_API_KEY=your_groq_api_key_here
   ```

### Running the Test

Run the test script from the root directory:

```bash
python test_sql_agent.py
```

### Expected Output

If successful, the script will print the generated request, invoke the LangGraph agent, and output a structured response that looks similar to this:

```text
Testing SQL Agent...

Sending Request Intent: Count the total number of records in the users table.
Target Tables: ['users']

=== Agent Response ===
Query Executed: SELECT COUNT(*) as total_users FROM users;
Validation Status: ValidationStatus.VALID
Row Count: 1
Results (first 5): [{'values': {'total_users': 150}}]
```

If there is an error (e.g., invalid API key, missing database table), the `Error:` section will be populated cleanly instead of crashing the script.
