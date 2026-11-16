# Руководство по использованию

[Быстрый пример](https://github.com/SbWereWolf/command-execution/blob/v1.0.1/README.ru.md)
· [English version](https://github.com/SbWereWolf/command-execution/blob/v1.0.1/docs/usage.md)

Требуется Python 3.11 или новее. Установка:
`python -m pip install "command-execution==1.0.1"`.

## Подготовка и выполнение команд

`plan_action(action, parameters, *, base_dir, interpreters)` проверяет и раскрывает
всё действие без запуска процессов. `execute_action` принимает те же аргументы,
сначала подготавливает всё действие, затем выполняет команды по порядку.

Полный пример передаёт параметр через окружение дочернего процесса:

```python
import sys
from pathlib import Path

from command_execution import execute_action, plan_action
from command_execution.actions.interpreters import exit_result

action = {
    "commands": [{
        "argv": [
            sys.executable, "-c",
            "import os; print(os.environ['GREETING'])",
        ],
        "cwd": ".",
        "env": {"GREETING": "${greeting}"},
        "interpreter": {"name": "exit", "options": {"accept": [0]}},
    }],
}
parameters = {"greeting": "Hello, Ada!"}
interpreters = {"exit": exit_result}
plan = plan_action(
    action, parameters, base_dir=Path.cwd(), interpreters=interpreters,
)
assert plan["commands"][0]["env"] == {"GREETING": "Hello, Ada!"}
result = execute_action(
    action, parameters, base_dir=Path.cwd(), interpreters=interpreters,
)
print(result["status"])
print(result["commands"][0]["stdout"].decode(), end="")
```

Результат:

```text
succeeded
Hello, Ada!
```

### Входные данные

| Аргумент | Значение |
| --- | --- |
| `action` | Объект со списком `commands`. Пустой список успешно завершается без процессов. |
| `parameters` | Карта строковых имён и значений `str`, `int`, `float` или `bool`. |
| `base_dir` | Явный абсолютный `str` или `Path`; относительные рабочие каталоги считаются от него. |
| `interpreters` | Карта имён и готовых объектов с методом `interpret(result, options)`. |

Каждая команда содержит все четыре поля:

| Поле | Значение |
| --- | --- |
| `argv` | Непустой список строк: исполняемый файл и его аргументы. |
| `cwd` | Строка рабочего каталога, абсолютная или относительно `base_dir`. |
| `env` | Полное строковое окружение процесса. Переменные хоста автоматически не добавляются. |
| `interpreter` | Объект с `name` и объектом `options`; имя разрешается в карте `interpreters`. |

В аргументах, `cwd` и значениях окружения однократно применяется Python
`string.Template`: `$name` или `${name}` подставляет параметр, `$$` обозначает
буквальный знак доллара. Настройки интерпретатора передаются как данные без
подстановки. Если в объявленном окружении нет `PATH`, используйте абсолютный
путь к исполняемому файлу, например `sys.executable`.

Процессы запускаются со списком аргументов и `shell=False`. Конвейеры,
перенаправления и другой синтаксис оболочки не исполняются. Стандартный ввод
закрыт. API дожидается каждого процесса и сохраняет его полный вывод; параметра
тайм-аута нет.

### Результаты и ошибки

План имеет вид `{"commands": [...]}` с раскрытыми аргументами, окружением и
разрешёнными рабочими каталогами. Планирование не проверяет существование
будущих исполняемых файлов и каталогов.

Выполнение возвращает объект:

| Поле | Значение |
| --- | --- |
| `status` | `"succeeded"` или `"failed"`. |
| `commands` | Записи о фактически предпринятых командах в порядке выполнения. |
| `error` | `None` при успехе, иначе строка с диагностикой. |

Запись команды содержит `invocation` (`argv`, `cwd`, `env`), `interpreter`,
`exit_code`, `stdout`, `stderr`, `interpretation` и `error`. Потоки вывода —
**байты**; декодируйте их в кодировке дочерней программы. Если процесс не удалось
запустить, `exit_code=None`, потоки пустые, а `error` содержит диагностику.

`exit_result` принимает ровно те коды, которые перечислены в `options["accept"]`.
При `[0]` ненулевой код означает ошибку действия, и следующие команды не
запускаются. Собственный интерпретатор может принимать другой код или проверять
вывод. Его метод `interpret(result, options)` возвращает объект с `success`
(логическое значение), `value` (любое значение Python) и `error` (`None` при
успехе, непустая строка при ошибке). Исключения и некорректные ответы
интерпретатора становятся ошибками команды. Предыдущие внешние эффекты не
откатываются.

Некорректная декларация, отсутствующий параметр подстановки, относительный
`base_dir` или неизвестный интерпретатор приводят к `ValueError` при подготовке,
до запуска любой команды. Ошибки запуска процесса возвращаются в результате
неуспешного выполнения.

## Чтение и изменение JSON-конфигураций

Главный JSON-документ сопоставляет имена операций путям к JSON-файлам в
`operations`. Относительные пути считаются от каталога главного файла.
Выбранный документ содержит список `requirements` из объектов с уникальными
непустыми строковыми `id`. Для операции `run` используется список `applications`.

Полный пример создаёт временные файлы, читает и изменяет элемент, затем удаляет
элементы. Чтение и редактирование сохранённых деклараций не запускает команды.

```python
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from command_execution import (
    add_requirement, clear_requirements, delete_requirement,
    list_requirement_ids, read_requirements, update_requirement,
)

with TemporaryDirectory() as directory:
    root = Path(directory)
    main = root / "main.json"
    items = root / "items.json"
    main.write_text(json.dumps({"operations": {"infra": "items.json"}}), encoding="utf-8")
    items.write_text(json.dumps({"owner": "demo", "requirements": []}), encoding="utf-8")

    add_requirement(main, "infra", {"id": "greet", "label": "Hello"})
    print(json.dumps(list_requirement_ids(main, "infra")))
    print(read_requirements(main, "infra", ["greet"])[0]["label"])
    update_requirement(main, "infra", "greet", [
        {"op": "replace", "path": "/label", "value": "Updated"},
    ])
    print(read_requirements(main, "infra", "all")[0]["label"])
    delete_requirement(main, "infra", "greet")
    add_requirement(main, "infra", {"id": "temporary"})
    clear_requirements(main, "infra")
    print(json.dumps(list_requirement_ids(main, "infra")))
    assert json.loads(items.read_text(encoding="utf-8"))["owner"] == "demo"
```

Результат:

```text
["greet"]
Hello
Updated
[]
```

### API конфигураций

Первые аргументы всех функций — `config_path` и `operation`.

| Функция | Остальные аргументы | Возвращаемое значение |
| --- | --- | --- |
| `list_requirement_ids` | Нет | ID в порядке документа. |
| `read_requirements` | `selection` | Полные копии объектов в выбранном порядке; `"all"` сохраняет порядок документа. |
| `add_requirement` | Полный объект `requirement` | `None`. |
| `update_requirement` | `identifier`, `changes` | `None`. |
| `delete_requirement` | `identifier` | `None`. |
| `clear_requirements` | Нет | `None`. |

`selection` — список уникальных строковых ID или строка `"all"`; `[]` выбирает
пустой набор. Отсутствующие выбранные ID, повторяющиеся ID или элементы выборки,
неизвестные операции, некорректный JSON и недоступные файлы приводят к `ValueError`.

`changes` — список операций JSON Patch: `add`, `replace` и `remove` с путями
JSON Pointer. Операции `copy`, `move` и `test` не поддерживаются. Каждая запись
сохраняет остальные элементы и метаданные документа, заменяя выбранный JSON-файл
через временный файл в том же каталоге. Нужны существующий доступный для записи
файл и каталог; отсутствующие документы конфигурации не создаются. Обрабатывайте
фактически возвращённый результат или ошибку записи.
