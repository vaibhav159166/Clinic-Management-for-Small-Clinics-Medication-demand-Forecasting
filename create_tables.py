import psycopg2
from psycopg2 import sql

# Database connection settings
DB_NAME = "Health"
DB_USER = "postgres"
DB_PASS = "root"

# Connect to PostgreSQL
def get_db_connection():
    conn = psycopg2.connect(database=DB_NAME, user=DB_USER, password=DB_PASS)
    return conn

def create_tables():
    conn = get_db_connection()
    cur = conn.cursor()

    # Drop existing tables (optional)
    for i in range(1, 7):
        table_name = f'clinic{i}_medication_data'
        cur.execute(sql.SQL("DROP TABLE IF EXISTS {}").format(sql.Identifier(table_name)))
    
    # Create new tables
    for i in range(1, 7):
        table_name = f'clinic{i}_medication_data'
        cur.execute(sql.SQL("""
            CREATE TABLE {} (
                id SERIAL PRIMARY KEY,
                date DATE NOT NULL,
                medication_name VARCHAR(255) NOT NULL,
                medication_demand INTEGER NOT NULL
            )
        """).format(sql.Identifier(table_name)))
    
    conn.commit()
    cur.close()
    conn.close()
    print("Tables created successfully!")

if __name__ == '__main__':
    create_tables()
