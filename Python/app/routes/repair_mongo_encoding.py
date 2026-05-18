import os
from dotenv import load_dotenv
from pymongo import MongoClient


load_dotenv()


def fix_text(value):
    if isinstance(value, str):
        try:
            fixed = value.encode("latin1").decode("utf-8")
            return fixed
        except Exception:
            return value

    if isinstance(value, list):
        return [fix_text(item) for item in value]

    if isinstance(value, dict):
        return {key: fix_text(val) for key, val in value.items()}

    return value


def main():
    host = os.getenv("MONGO_HOST", "192.168.56.101")
    port = int(os.getenv("MONGO_PORT", "27018"))
    db_name = os.getenv("MONGO_DB", "sgec_logs")

    client = MongoClient(f"mongodb://{host}:{port}/{db_name}")
    db = client[db_name]

    collections = [
        "audit_logs",
        "eventos_asignacion",
        "estadisticas",
        "eventos_seguridad",
        "assignment_events",
        "security_events",
    ]

    total_actualizados = 0

    for collection_name in collections:
        collection = db[collection_name]

        for doc in collection.find({}):
            original_id = doc["_id"]
            fixed_doc = fix_text(doc)

            if fixed_doc != doc:
                collection.replace_one({"_id": original_id}, fixed_doc)
                total_actualizados += 1

        print(f"Revisada colección: {collection_name}")

    print(f"Corrección terminada. Documentos actualizados: {total_actualizados}")


if __name__ == "__main__":
    main()