# Руководство по использованию

[Быстрый пример](https://github.com/SbWereWolf/command-execution/blob/master/README.ru.md)
· [English reference](https://github.com/SbWereWolf/command-execution/blob/master/docs/usage.md)

## Подготовка и выполнение команд

`CommandPlanner.compile` получает JSON-документ и возвращает план и список ошибок.
`ChainCoordinator.run` выполняет подготовленный план и ожидает завершения всех
запущенных команд. Команды могут создавать произвольные сторонние эффекты;
библиотека не отменяет их автоматически.

### Входные данные

Корневой объект содержит массив `commands`. У команды есть `argv`, необязательный
`id`, `order`, `execution` (`sync`/`async`) и `on_error` (`stop`/`continue`).
`sync-mode` и `batch-mode` задаются массивами из `std-out`/`std-err`, включая пустой
массив. Произвольные дополнительные свойства сохраняются для потребителя.
Рабочий каталог, окружение, перенаправления, таймауты и сигналы задаёт потребитель
в своей составной команде или специализированном скрипте.

```python
from command_execution import CommandPlanner, ChainCoordinator

plan, issues = CommandPlanner().compile({"commands": [
    {"id": "first", "argv": ["printf", "first"], "order": 2},
    {"id": "second", "argv": ["printf", "second"], "order": 1}
]})
assert not issues
started_order = []
result = ChainCoordinator(plan).run({"input": False}, on_result=lambda row: started_order.append(row.id))
assert started_order == ["second", "first"]
assert [row.id for row in result.commands] == ["first", "second"]
assert {row.id: row.raw.stdout for row in result.commands} == {
    "first": b"first", "second": b"second"}
assert result.status == "succeeded"
print(result.status)
```

### Результаты и ошибки

Результат сохраняет вход, исходный индекс, фактические байты stdout/stderr,
код завершения и интерпретацию каждой попытки. Исходный порядок хранения записей
не подменяет порядок запуска из `order`. Интерпретатор определяет успех;
`next_input` изменяет вход следующей синхронной команды после проверки JSON.
Асинхронные результаты не изменяют этот синхронный поток данных.

`on_error=continue` сохраняет ошибку и допускает последующие запуски. `stop`
останавливает ещё не начатые команды после обнаружения ошибки, сохраняя уже
произошедшие эффекты. При отказе создания async worker сохраняется отдельный
`dispatch_failed` с `raw=None`; выдуманных байтов или кода дочернего процесса нет.
Режим CLI выводит JSONL-события с типом потока `out`/`err`; бинарные данные
передаются обратимо. `command-execution validate` собирает все ошибки конфигурации
без запуска команд. Полная схема событий и правила подстановок даны в English reference.

## Чтение и изменение JSON-конфигураций

CE обрабатывает JSON-значения в памяти. Чтение/сохранение файлов и создание
каталогов выполняются средствами потребителя. `JSONCodec` задаёт профиль JSON,
`DocumentCollection` — CRUD и порядок элементов, `JSONPathEditor` — вложенные
изменения, `JSONMerger` — объединение. Потребитель толкует свои дополнительные
свойства дочерних объектов.

### API конфигураций

```python
from command_execution import DocumentCollection

original = {"commands": [{"id": "a", "argv": ["true"], "owner": {"ticket": 2}}]}
updated = DocumentCollection(original, "commands").add({"id": "b", "argv": ["true"]})
updated = updated.move("b", 0)
assert updated.ids() == ["b", "a"]
assert original["commands"] == [{"id": "a", "argv": ["true"], "owner": {"ticket": 2}}]
assert updated.document()["commands"][1]["owner"] == {"ticket": 2}
print(updated.ids())
```

[Полный справочник параметров, коллекций и исполнения](https://github.com/SbWereWolf/command-execution/blob/master/docs/usage.md).
