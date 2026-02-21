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

    def get_rows_from_table_with_value(self, table, column, value):
        """
        Returns all rows from `table` where `column` equals `value`.
        """
        cursor = self.conn.cursor()
        query = f"SELECT * FROM {table} WHERE {column} = %s"
        cursor.execute(query, (value,))
        return cursor.fetchall()
    
    def insert_row(self, table_name, column_names, placeholders_or_values, values=None):
        """
        Insert a row into a table.
        Supports two call styles:
        1. insert_row(table_name, ("col1","col2"), (val1, val2))
        2. insert_row(table_name, "(col1, col2)", "(%s, %s)", (val1, val2))

        Args:
            table_name: Name of the table
            column_names: tuple/list of column names OR a string like "(col1, col2)"
            placeholders_or_values: if `values` is None -> this is the tuple of values (style 1).
                                    if `values` is not None -> this is the placeholders string e.g. "(%s, %s)" (style 2).
            values: tuple of values when using style 2. (optional)
        """
        if not self.database:
            raise ValueError("No database selected.")

        # Determine which call style is being used
        if values is None:
            # style 1: column_names can be tuple/list or string with parens,
            # placeholders_or_values is the values tuple
            vals = tuple(placeholders_or_values)
            # columns handling
            if isinstance(column_names, (list, tuple)):
                cols = ", ".join(column_names)
            elif isinstance(column_names, str):
                cols = column_names.strip()
                if cols.startswith("(") and cols.endswith(")"):
                    cols = cols[1:-1].strip()
            else:
                raise TypeError("column_names must be a list/tuple or a parenthesized string.")
            # build placeholders automatically from values length
            placeholders_inner = ", ".join(["%s"] * len(vals))
        else:
            # style 2: placeholders_or_values is a placeholders string like "(%s, %s)"
            vals = tuple(values)
            placeholders = str(placeholders_or_values).strip()
            # normalize placeholders: remove surrounding parentheses if present
            if placeholders.startswith("(") and placeholders.endswith(")"):
                placeholders_inner = placeholders[1:-1].strip()
            else:
                placeholders_inner = placeholders
            # columns handling: column_names should be string or iterable
            if isinstance(column_names, (list, tuple)):
                cols = ", ".join(column_names)
            elif isinstance(column_names, str):
                cols = column_names.strip()
                if cols.startswith("(") and cols.endswith(")"):
                    cols = cols[1:-1].strip()
            else:
                raise TypeError("column_names must be a list/tuple or a parenthesized string.")

        # Final SQL and execution
        cursor = self.conn.cursor()
        query = f"INSERT INTO {table_name} ({cols}) VALUES ({placeholders_inner})"
        cursor.execute(query, vals)
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
