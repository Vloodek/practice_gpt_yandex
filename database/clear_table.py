from sqlalchemy import create_engine, MetaData, Table
from sqlalchemy.orm import sessionmaker

# Настройте ваше соединение с базой данных
DATABASE_URL = "sqlite:///test.db"
engine = create_engine(DATABASE_URL)
metadata = MetaData()

# Создайте сессию
Session = sessionmaker(bind=engine)
session = Session()

def get_table_choice():
    print("Выберите таблицу для очистки:")
    print("1. generation_history")
    print("2. users")
    print("3. sessions")
    choice = input("Введите номер таблицы (1, 2, 3): ")
    return choice

def clear_table(table_name):
    table = Table(table_name, metadata, autoload_with=engine)
    try:
        session.execute(table.delete())
        session.commit()
        print(f"Таблица {table_name} успешно очищена.")
    except Exception as e:
        session.rollback()
        print(f"Произошла ошибка: {e}")
    finally:
        session.close()

def main():
    choice = get_table_choice()
    if choice == '1':
        clear_table('generation_history')
    elif choice == '2':
        clear_table('users')
    elif choice == '3':
        clear_table('sessions')
    else:
        print("Неправильный выбор. Пожалуйста, выберите 1, 2 или 3.")

if __name__ == "__main__":
    main()
