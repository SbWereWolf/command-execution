"""Pure configuration, command coordination and structured execution results."""
__version__ = '2.0.8'

from .json_codec import JSONCodec
from .json_paths import JSONPathEditor, JSONMerger
from .collections import DocumentCollection
from .parameters import ParameterLookup, TemplateRenderer, DeferredResolver
from .command_model import CommandSpec, RawOutcome, CommandOutcome, ChainResult, OutputChunk, CommandPlan
from .configuration import CommandPlanner, OutputSelection, OutputStreams, ConfigurationIssue
from .results import ResultStore, MemoryResultStore, DispatchResultView
from .error_policy import ErrorPolicy
from .delivery import OutputDelivery, JSONLWriter
from .lists import ListCoordinator, CallListRunner
from .execution import ProcessWorker, ChainCoordinator, ChainRun
