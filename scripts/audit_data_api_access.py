"""Read-only catalog audit. Does not apply the reviewed SQL integration plan."""
from dataclasses import asdict
import json

from app.core.config import Settings
from app.core.database import create_database_engine
from app.infrastructure.database.data_api_security import assess_access, inspect_access


def main() -> int:
    engine = None
    try:
        engine = create_database_engine(Settings(), connect_args={"connect_timeout": 8})
        with engine.connect() as connection:
            connection.exec_driver_sql("SET TRANSACTION READ ONLY")
            if connection.exec_driver_sql("SHOW transaction_read_only").scalar_one() != "on":
                raise RuntimeError("Read-only transaction required")
            findings = assess_access(inspect_access(connection))
        print(json.dumps({"findings": [asdict(finding) for finding in findings]}, ensure_ascii=False))
        return 1 if findings else 0
    except Exception:
        # Driver exceptions can contain server details, URLs or rejected values.
        print("Não foi possível concluir a inspeção de permissões somente leitura.")
        return 2
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
