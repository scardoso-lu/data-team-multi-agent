class ProviderRegistry:
    def __init__(self, providers=None):
        self._providers = []
        for provider in providers or []:
            self.register(provider)

    def register(self, provider):
        self._providers.append(provider)
        return provider

    def ordered(self, names=None):
        if names is None:
            return list(self._providers)
        wanted = list(names)
        return [provider for name in wanted for provider in self._providers if provider.name == name]

    def names(self):
        return [provider.name for provider in self._providers]
