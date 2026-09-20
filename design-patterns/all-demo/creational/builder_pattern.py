"""
Summary: Implements the Builder pattern to construct complex objects step-by-step.
Avoids constructors with many optional arguments and makes configuration
code much more readable and maintainable.
"""


class ServerConfig:
    def __init__(self):
        self.host = "localhost"
        self.port = 8080
        self.use_ssl = False
        self.max_workers = 4

    def __str__(self):
        return f"Server(host={self.host}, port={self.port}, ssl={self.use_ssl}, workers={self.max_workers})"


class ServerConfigBuilder:
    def __init__(self):
        self._config = ServerConfig()

    def set_host(self, host: str) -> "ServerConfigBuilder":
        self._config.host = host
        return self

    def set_port(self, port: int) -> "ServerConfigBuilder":
        self._config.port = port
        return self

    def enable_ssl(self) -> "ServerConfigBuilder":
        self._config.use_ssl = True
        return self

    def set_workers(self, count: int) -> "ServerConfigBuilder":
        self._config.max_workers = count
        return self

    def build(self) -> ServerConfig:
        return self._config


if __name__ == "__main__":
    # Fluent interface for building complex config
    config = (
        ServerConfigBuilder()
        .set_host("0.0.0.0")
        .set_port(3000)
        .enable_ssl()
        .set_workers(8)
        .build()
    )

    print(config)
