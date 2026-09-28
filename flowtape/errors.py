class FlowTapeError(Exception):
    """A user-facing, non-secret FlowTape failure."""


class DriverConfigurationError(FlowTapeError):
    pass


class BrowserStartupError(FlowTapeError):
    pass


class ScenarioValidationError(FlowTapeError):
    pass


class UnknownPage(FlowTapeError):
    pass


class AmbiguousPage(FlowTapeError):
    pass


class TargetNotFound(FlowTapeError):
    pass


class AmbiguousTarget(FlowTapeError):
    pass


class TargetContextError(FlowTapeError):
    pass


class ActionCompatibilityError(FlowTapeError):
    pass


class WaitTimeout(FlowTapeError):
    pass


class LoopLimitExceeded(FlowTapeError):
    pass


class CredentialOutputForbidden(FlowTapeError):
    pass


class OutputSchemaMismatch(FlowTapeError):
    pass


class OutputWriteError(FlowTapeError):
    pass


class CollectionMemberNotFound(FlowTapeError):
    pass


class CollectionMemberAmbiguous(FlowTapeError):
    pass


class CollectionContextUnavailable(FlowTapeError):
    pass


class BrowserContextError(FlowTapeError):
    pass


class UnsupportedOperationError(FlowTapeError):
    pass


class PlaybackStopped(FlowTapeError):
    pass
