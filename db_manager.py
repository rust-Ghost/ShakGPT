from datetime import datetime
from mysql.connector import connect

class DatabaseManager:
    def __init__(self, host, user, password, database=None):
        self.host = host
        self.user = user
        self.password = password
        self.database = database
        self.conn = None
        self._connect()

    def _connect(self):
        if self.database:
            self.conn = connect(
                host=self.host,
                user=self.user,
                password=self.password,
                database=self.database
            )
        else:
            self.conn = connect(
                host=self.host,
                user=self.user,
                password=self.password
            )

    def reconnect(self, database=None):
        if self.conn:
            self.conn.close()
        if database:
            self.database = database
        self._connect()

    def show_databases(self):
        cursor = self.conn.cursor()
        cursor.execute("SHOW DATABASES")
        return [db[0] for db in cursor]

    def create_database(self, db_name):
        if db_name not in self.show_databases():
            cursor = self.conn.cursor()
            cursor.execute(f"CREATE DATABASE {db_name}")
            print(f"Database {db_name} created successfully.")

    def show_tables(self):
        if not self.database:
            raise ValueError("No database selected.")
        cursor = self.conn.cursor()
        cursor.execute("SHOW TABLES")
        return [table[0] for table in cursor]

    def create_table(self, table_name, params):
        """
        Create a new table if it doesn't exist.
        
        Args:
            table_name: Name of the table to create
            params: SQL parameters for table creation (columns, types, constraints)
        """
        if not self.database:
            raise ValueError("No database selected.")
        cursor = self.conn.cursor()
        query = f"CREATE TABLE IF NOT EXISTS {table_name} {params}"
        cursor.execute(query)
        self.conn.commit()
        print(f"Table {table_name} ensured to exist.")

    def delete_table(self, table_name):
        if not self.database:
            raise ValueError("No database selected.")
        cursor = self.conn.cursor()
        query = f"DROP TABLE IF EXISTS {table_name}"
        cursor.execute(query)
        self.conn.commit()
        print(f"Table {table_name} dropped if it existed.")

    def insert_row(self, table_name, column_names, values):
        """
        Insert a row into a table.
        
        Args:
            table_name: Name of the table
            column_names: Tuple of column names, e.g., ("id", "name")
            values: Tuple of values to insert, e.g., (1, "Alice")
        """
        if not self.database:
            raise ValueError("No database selected.")
        cursor = self.conn.cursor()
        placeholders = ", ".join(["%s"] * len(values))
        columns = ", ".join(column_names)
        query = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"
        cursor.execute(query, values)
        self.conn.commit()
        print(f"Row inserted into {table_name} successfully.")

    def get_all_rows(self, table_name):
        if not self.database:
            raise ValueError("No database selected.")
        cursor = self.conn.cursor()
        cursor.execute(f"SELECT * FROM {table_name}")
        return cursor.fetchall()

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None
            print("Database connection closed.")
