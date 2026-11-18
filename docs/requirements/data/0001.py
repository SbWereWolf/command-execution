from yoyo import step

__depends__ = set()
__transactional__ = True
steps = [step('INSERT INTO requirements_meta(revision) VALUES(0);', 'DELETE FROM requirements_meta;')]
