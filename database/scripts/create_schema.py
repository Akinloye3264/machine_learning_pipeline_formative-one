import os
from pathlib import Path

import mysql.connector
from dotenv import load_dotenv
# Get the main project folder
ROOT = Path(__file__).resolve().parent.parent.parent
# Find the SQL file
SCHEMA_FILE = ROOT / "database" /"sql" / "schema.sql"

def split_statements(sql_text):
    lines = []

    for line in sql_text.splitlines():
        if not line.strip().startswith("--"):
            lines.append(line)

    sql_text = "\n".join(lines)
    print(lines)
    statements = []
    for statement in sql_text.split(";"):
        statement = statement.strip()

        if statement:
            statements.append(statement)
    print(statements)
    return statements


def main():
    # Load environment variables
    load_dotenv(ROOT / ".env")

    # Connect to MySQL
    conn = mysql.connector.connect(
        host=os.getenv("MYSQL_HOST"),
        port=int(os.getenv("MYSQL_PORT")),
        user=os.getenv("MYSQL_USER"),
        password=os.getenv("MYSQL_PASSWORD"),
    )
    cursor = conn.cursor()
    try:
        # Read the SQL file
        with open(SCHEMA_FILE, "r") as file:
            sql_text = file.read()

        # Execute each SQL statement
        statements = split_statements(sql_text)

        for statement in statements:
            cursor.execute(statement)

        conn.commit()

        # Select the database
        database = os.getenv("MYSQL_DATABASE", "traffic_db")
        cursor.execute("USE " + database)

        # Display the created tables
        cursor.execute("SHOW TABLES;")

        tables = cursor.fetchall()

        print("Database schema created successfully!")
        print("Tables created:")

        for table in tables:
            print(table[0])

    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    main()
