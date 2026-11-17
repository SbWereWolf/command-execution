from yoyo import step

__depends__ = {'0001'}
__transactional__ = True
steps = [
    step("INSERT INTO requirements(id,level,status,text) VALUES ('SYS-CE-USAGE','system','current','Пользователь библиотеки получает доступное описание её назначения и проверяемые примеры применения.');", ''),
    step("INSERT INTO requirements(id,level,status,text) VALUES ('APP-CE-PACKAGE-DOCS','application','current','Страница пакета и подробное руководство объясняют назначение и стабильный API на английском языке, предоставляют рабочий пример и ссылку на русскую версию.');", ''),
    step("INSERT INTO requirement_links(system_id,application_id) VALUES ('SYS-CE-USAGE','APP-CE-PACKAGE-DOCS');", ''),
    step('UPDATE requirements_meta SET revision=1;', ''),
    step('', 'UPDATE requirements_meta SET revision=0;'),
    step('', "DELETE FROM requirements WHERE id IN ('SYS-CE-USAGE','APP-CE-PACKAGE-DOCS');"),
    step('', "DELETE FROM requirement_links WHERE system_id='SYS-CE-USAGE' AND application_id='APP-CE-PACKAGE-DOCS';"),
]
