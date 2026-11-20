"""The queue between the Broker's thread and the Universe's thread."""

from spaceknowledge.common.messages import Request, Response
from spaceknowledge.transport.work_queue import ServerStoppedError, Ticket, WorkQueue

__all__ = ["CallQueue", "PendingCall", "ServerStoppedError"]


class PendingCall(Ticket[Request, Response]):
    """A request waiting for its answer: a Ticket that only accepts a Request
    and answers with a Response."""

    def __init__(self, request: Request) -> None:
        if not isinstance(request, Request):
            raise TypeError(f"request must be a Request, not {type(request).__name__}")
        super().__init__(request)

    @property
    def request(self) -> Request:
        return self.payload

    def complete(self, response: Response) -> None:
        if not isinstance(response, Response):
            raise TypeError(f"response must be a Response, not {type(response).__name__}")
        super().complete(response)


class CallQueue(WorkQueue[PendingCall]):
    """The Universe thread's queue. Only accepts PendingCalls."""

    def push(self, call: PendingCall) -> None:
        if not isinstance(call, PendingCall):
            raise TypeError(f"call must be a PendingCall, not {type(call).__name__}")
        super().push(call)