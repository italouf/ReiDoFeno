import factory

from accounts.models import Usuario


class UsuarioFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Usuario
        django_get_or_create = ("username",)

    username = factory.Sequence(lambda n: f"usuario{n}")
    email = factory.LazyAttribute(lambda o: f"{o.username}@reidofeno.com.br")
    first_name = factory.Faker("first_name", locale="pt_BR")
    last_name = factory.Faker("last_name", locale="pt_BR")
    telefone = factory.Sequence(lambda n: f"(75) 9{n:04d}-{n * 7919 % 10000:04d}")
    perfil = Usuario.Perfil.CLIENTE
    password = factory.PostGenerationMethodCall("set_password", "senha-forte-123")

    @factory.post_generation
    def grupos(self, create, extracted, **kwargs):
        if not create:
            return
        if extracted:
            for grupo in extracted:
                self.groups.add(grupo)
