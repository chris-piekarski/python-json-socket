# Design Patterns in JSocket

This repo uses a few classic object-oriented design patterns. The diagrams below map directly to the current class structure and control flow.

## Template Method (Message Processing Loop)

`ThreadedServer` and `ServerFactoryThread` define the skeleton of a read-process-respond loop, and delegate the message-specific behavior to `_process_message`, which subclasses implement.

```mermaid
flowchart TD
    A["ThreadedServer run"] --> B["handle client messages"]
    B --> C["read obj"]
    C --> D["process message"]
    D --> E{response}
    E -->|yes| F["send obj"]
    E -->|no| G["continue loop"]
```

```mermaid
classDiagram
    class ThreadedServer {
        +run()
        +handle_client_messages()
        #process_message(obj)
    }
    class EchoServer {
        +process_message(obj)
    }
    ThreadedServer <|-- EchoServer
```

## Factory (Thread-per-Connection Workers)

`ServerFactory` accepts a `ServerFactoryThread` subclass and instantiates a new worker per connection. This is effectively a factory for connection handlers.

```mermaid
classDiagram
    class ServerFactory {
        -thread_type
        +run()
    }
    class ServerFactoryThread {
        +swap_socket(sock)
        +run()
        #process_message(obj)
    }
    ServerFactory --> ServerFactoryThread : creates
```

## Facade (Simplified Public API)

The top-level `jsocket` package re-exports the primary classes so callers can import from a single module instead of multiple internal modules.

```mermaid
flowchart LR
    A["Application Code"] --> B["jsocket package"]
    B --> C["jsocket_base JsonSocket"]
    B --> D["jsocket_base JsonServer"]
    B --> E["jsocket_base JsonClient"]
    B --> F["tserver ThreadedServer"]
    B --> G["tserver ServerFactory"]
```
