# command-execution

Python-библиотека для приложений, которые описывают команды в JSON: упорядочить
список, подставить параметры, выполнить команды и получить структурированные
результаты. Она также изменяет коллекции и вложенные JSON-значения в памяти.
Требуется Python 3.11 или новее.

[English README](https://github.com/SbWereWolf/command-execution/blob/master/README.md)
— основное описание пакета.

## Установка

Из выбранной рабочей копии в подготовленное окружение Python:

```bash
python -m pip install .
```

Для установки из индекса выберите доступную опубликованную версию 2.x.
[Выбор версии и проверка установки](https://github.com/SbWereWolf/command-execution/blob/master/docs/maintenance.md).

## Быстрый пример

Пример запускает настоящий процесс и проверяет полученные байты:

```python
from command_execution import CommandPlanner, ChainCoordinator

plan, issues = CommandPlanner().compile({"commands": [
    {"id": "hello", "argv": ["printf", "Hello from CE\n"], "execution": "sync"}
]})
assert not issues
result = ChainCoordinator(plan).run(None)
assert result.status == "succeeded"
assert result.commands[0].raw.stdout == b"Hello from CE\n"
print(result.commands[0].raw.stdout.decode(), end="")
```

## Подробная документация

- [Руководство на русском](https://github.com/SbWereWolf/command-execution/blob/master/docs/usage.ru.md).
- [Полный справочник CLI и Python API](https://github.com/SbWereWolf/command-execution/blob/master/docs/usage.md).
- [Установка и сопровождение](https://github.com/SbWereWolf/command-execution/blob/master/docs/maintenance.md).
