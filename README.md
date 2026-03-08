# Academiaa - MVP

Aplicacao web em `Python + Flask + HTML + CSS` para:

- Controle de treino por dia, exercicios e series
- Controle de suplementacao com previsao de duracao
- Registro de medidas corporais com comparativo

## Como executar

1. Instale dependencias:

```bash
pip install flask werkzeug
```

2. Rode o servidor:

```bash
python app.py
```

3. Acesse:

`http://127.0.0.1:5000`

## Login inicial

- Usuario: `admin`
- Senha: `admin123`

Use o menu `Usuarios` (admin) para criar logins de clientes.

## Observacoes

- Banco local SQLite: `academia.db` (criado automaticamente).
- Troque `SECRET_KEY` e a senha do admin antes de publicar em producao.

## Publicar na internet (gratis)

Opcao simples: Render (Web Service).

1. Suba este projeto para um repositorio no GitHub.
2. Crie conta em `render.com`.
3. New + Web Service + conecte o repositorio.
4. Configuracoes:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn app:app`
5. Deploy.

Importante sobre SQLite em hospedagem gratis:
- Pode perder dados em reinicio/redeploy.
- Para producao real, use banco gerenciado (PostgreSQL).
