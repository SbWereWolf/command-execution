"""JSON-in/JSONL-out command execution; callers own filesystem and shell policy."""
import argparse
import json
import sys
from .configuration import CommandPlanner
from .execution import ChainCoordinator
from .delivery import JSONLWriter, OutputDelivery


def main(argv=None):
    parser = argparse.ArgumentParser(prog='command-execution')
    parser.add_argument('operation', choices=('run', 'validate'))
    args = parser.parse_args(argv)
    writer = JSONLWriter(sys.stdout)

    def validation_result(issue_count):
        writer.emit({'event': 'validation_result', 'valid': issue_count == 0,
            'status': 'valid' if issue_count == 0 else 'invalid', 'issue_count': issue_count})

    try:
        try:
            if sys.stdin is None:
                raise ValueError('Standard input is unavailable')
            document = json.load(sys.stdin)
            plan, issues = CommandPlanner().compile(document,
                parameters=document.get('parameters', {}) if isinstance(document, dict) else {},
                validation=args.operation == 'validate')
        except (ValueError, TypeError, OSError, RecursionError) as error:
            writer.emit({'event': 'configuration_issue', 'code': 'invalid_document', 'message': str(error)})
            if args.operation == 'validate':
                validation_result(1)
            return 2
        if args.operation == 'validate' or plan is None:
            for issue in issues:
                writer.emit({'event': 'configuration_issue', **vars(issue)})
            if args.operation == 'validate':
                validation_result(len(issues))
            return 2 if issues else 0
        coordinator = ChainCoordinator(plan)
        coordinator.delivery = OutputDelivery(coordinator.store, emit=writer.emit)
        result = coordinator.run(document.get('input'))
        return 0 if result.status == 'succeeded' else 1
    finally:
        writer.close()


if __name__ == '__main__':
    raise SystemExit(main())
