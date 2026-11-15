# command-execution

Самостоятельная Python-библиотека подготовки и выполнения команд и изменения
декларативных конфигураций. Требуется Python 3.11 или новее.

После публикации выбранная версия устанавливается через менеджер пакетов:

```bash
python -m pip install 'command-execution==1.1.0'
```

Исходники выделены с историей из `environment-maintenance/packages/command-execution`.
Первый самостоятельный выпуск — **1.0.0**, тег **v1.0.0**. Исторический bootstrap
с metadata 0.1.0 не является этим выпуском.

## Однократная настройка публикации

Локальная рабочая копия: `/home/sbwerewolf/workdata/command-execution`.
Локальный bare: `/mnt/d/WORK/kv1me/planing/command-execution.git`, remote `bare-local`.
GitHub-репозиторий создаёт владелец из этой рабочей копии; его адрес затем добавляется
как `origin`. Эти адреса описывают текущую установку, а не обязательное расположение
для других разработчиков.

В PyPI настройте pending/обычный Trusted Publisher для проекта `command-execution`:
фактические владелец и GitHub-репозиторий, workflow `publish.yml`, environment `pypi`.
В GitHub создайте соответствующий environment. Workflow получает OIDC identity;
API-токен и ручная загрузка wheel не требуются. Доступность имени и права на проект
подтверждаются владельцем в PyPI до первого push тега.

## Выпуск

1. Измените обе версии: `pyproject.toml` и `src/command_execution/__init__.py`.
   Обновите буквальные ожидания выпуска в тестах и фикстурах для новой версии.
2. Выполните `python -I -B tests/test_release_contract.py -v`, сохраните commit
   с workflow и согласованными metadata. Собирайте локально из временной копии
   отслеживаемых файлов этого commit: backend создаёт `egg-info` и `build` в source.
3. Создайте annotated тег, например `git tag -a v1.0.0 -m 'Release 1.0.0'`,
   сохраните ветку и тег в `bare-local`. После настройки origin и publisher
   отправьте ветку и **этот же** тег в origin: `git push origin master v1.0.0`.

Push тега запускает проверки, сборку wheel и публикацию в PyPI. Тег обязан
указывать на commit, уже содержащий workflow. GitHub Release и ручной архив
для этого маршрута не нужны. Не передвигайте опубликованный тег.

## Повтор и отказ

Реестр проверяется read-only GET по точным имени и версии. Только HTTP 404
разрешает первую публикацию. Уже опубликованный точный набор файлов с теми же
SHA-256 даёт успешный пропуск загрузки. Отличающиеся или неполные файлы,
отказ доступа и сетевая ошибка останавливают выпуск с диагностикой.
Для воспроизводимого wheel workflow использует время commit в SOURCE_DATE_EPOCH.
Изменение backend может изменить байты: в таком случае выпускайте новую версию.

После прерванного запуска сначала проверьте Actions и фактические файлы PyPI;
повторите тот же workflow при тех же исходниках. Не обходите конфликт заменой
тега или ручной перезаписью файлов. После публикации выбранного выпуска проверьте его чистую установку; до неё доступность версии в PyPI не считается подтверждённой.

Ссылки: [Trusted Publishing](https://docs.pypi.org/trusted-publishers/using-a-publisher/),
[API версии](https://docs.pypi.org/api/json/#get-a-release).

## Цепочки с передачей данных

Версия 1.1.0 добавляет `plan_chain` и `execute_chain` к прежним API. Текущие
исходники выбирают 1.1.0; первый самостоятельный выпуск 1.0.0 и приведённый выше
пример его тега остаются историей. Новый исходник/локальный кандидат не означает
публикацию в PyPI или обновление установленных потребителей.

Обе функции получают `action`, `parameters` и именованные `input_data`,
`base_dir`, `interpreters`. `execute_chain` дополнительно принимает необязательные
`run_command` и `on_result`. Команда задаёт `argv/cwd/env/interpreter`,
`mode` (`sync` по умолчанию либо `async`), `enabled` (True), `on_error`
(`stop` по умолчанию либо `continue`). Подстановки используют исходные
parameters, текущий JSON-вход идёт в stdin. Только явный JSON-пригодный
`next_input` из интерпретатора меняет данные; value остаётся отдельным.
Отсутствие ключа сохраняет вход, False/0/пустое значение/None передаются явно.
`plan_chain` готовит все записи без процессов, потоков и интерпретации;
отключённые записи остаются в плане и пропускаются при исполнении.

Успех определяет интерпретатор. Sync stop прекращает проход, continue продолжает
с допустимым next_input либо последним корректным входом, сохраняя failed и
первую ошибку. Async получает глубокий снимок, немедленно пропускает прежний вход
дальше и никогда не меняет поздним результатом data/status/error цепочки.

Результат содержит status/data/commands/error; записи — полные bytes потоков,
фактический exit_code, interpretation и exception type/message. Пока async
работает, неизвестные поля равны None. При отказе создания/запуска потока запись
уже completed, но stdout/stderr/exit_code/interpretation остаются None; error
и exception сохраняют причину, цепочка продолжается. Completed не гарантирует
bytes. `on_result` получает копию завершённой записи в calling thread для sync
и dispatch failure, в worker для обычного async completion. Consumer обеспечивает
короткий невыбрасывающий callback/собственную очередь журнала и время жизни
runtime. Недемонический worker может удерживать завершение Python-процесса;
принудительное убийство процесса не гарантирует доставку журнала.

Подсказка: задайте `LIBRARY_PYTHON` установленной выбранной библиотеки; остальные
аргументы примера полные. `input_data` — JSON, `base_dir` — абсолютная база cwd,
`interpreters` — объекты с interpret. [Исходник публичного API](src/command_execution/actions/chain.py).

```bash
"${LIBRARY_PYTHON:?Выберите Python библиотеки 1.1.0}" -I -B - <<'PY'
import json
from pathlib import Path
import sys
from command_execution import plan_chain, execute_chain

class Increment:
    def interpret(self, raw, options):
        received = json.loads(raw["stdout"])
        return {"success": True, "value": "separate-value", "error": None,
                "next_input": {"number": received["number"] + 1}}

command = {
    "argv": [sys.executable, "-B", "-c",
             "import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())"],
    "cwd": ".", "env": {},
    "interpreter": {"name": "increment", "options": {}}
}
action = {"commands": [command, command]}
arguments = dict(input_data={"number": 3}, base_dir=Path.cwd(),
                 interpreters={"increment": Increment()})
plan = plan_chain(action, {}, **arguments)  # dry-run: no child starts
assert [row["mode"] for row in plan["commands"]] == ["sync", "sync"]
records = []
result = execute_chain(action, {}, on_result=records.append, **arguments)
assert result["status"] == "succeeded"
assert result["data"] == {"number": 5}
assert [json.loads(row["stdout"]) for row in records] == [{"number": 3}, {"number": 4}]
assert [row["exit_code"] for row in records] == [0, 0]
print(json.dumps({"data": result["data"],
                  "stdout_hex": [row["stdout"].hex() for row in records]}))
PY
```
