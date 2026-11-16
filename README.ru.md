# command-execution

Запускайте внешние команды из Python по явным декларациям, которые можно
использовать повторно. Подготовьте аргументы, рабочие каталоги и переменные
окружения до запуска процессов, задайте успешные коды завершения и получите
фактический вывод.

Библиотека подходит для шагов сборки, локальной автоматизации и инструментов,
которые хранят команды в JSON. Она также читает и изменяет такие конфигурации:
выбирает элементы по ID, добавляет их, обновляет поля через JSON Patch и удаляет
элементы.

Требуется **Python 3.11 или новее**.

## Установка

```sh
python -m pip install "command-execution==1.0.1"
```

## Быстрый пример

Пример запускает настоящий дочерний процесс Python и выводит результат:

```python
import sys
from pathlib import Path

from command_execution import execute_action
from command_execution.actions.interpreters import exit_result

action = {
    "commands": [{
        "argv": [sys.executable, "-c", "print('Hello from command-execution')"],
        "cwd": ".",
        "env": {},
        "interpreter": {"name": "exit", "options": {"accept": [0]}},
    }],
}
result = execute_action(
    action, {},
    base_dir=Path.cwd(),
    interpreters={"exit": exit_result},
)
print(result["status"])
print(result["commands"][0]["stdout"].decode(), end="")
```

Результат:

```text
succeeded
Hello from command-execution
```

Каждая команда задаёт список аргументов, рабочий каталог, полное окружение и
интерпретатор результата. Команды выполняются по порядку; запуск останавливается
при первой ошибке запуска или непринятом результате. `stdout` и `stderr`
сохраняются как байты, а `exit_code` содержит фактический код завершения процесса.

## Подробная документация

[Руководство](https://github.com/SbWereWolf/command-execution/blob/v1.0.1/docs/usage.ru.md)
объясняет подстановку параметров, планирование без выполнения, поля результата,
обработку ошибок и содержит полный пример работы с JSON-конфигурацией.

| API | Назначение |
| --- | --- |
| `plan_action` | Подставить параметры и проверить декларацию без запуска процессов. |
| `execute_action` | Подготовить и выполнить команды, вернуть вывод и интерпретированные результаты. |
| `list_requirement_ids`, `read_requirements` | Прочитать выбранные элементы конфигурации. |
| `add_requirement`, `update_requirement` | Добавить элемент или изменить его через JSON Patch. |
| `delete_requirement`, `clear_requirements` | Удалить один элемент или очистить выбранный список. |

[English version](https://github.com/SbWereWolf/command-execution/blob/v1.0.1/README.md)
· [English usage guide](https://github.com/SbWereWolf/command-execution/blob/v1.0.1/docs/usage.md)
