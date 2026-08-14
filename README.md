# Minato Inventory — deploy clean

Versão mínima do aplicativo para deploy/teste.

## Executar localmente

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

O banco atual está em `data/inventory.db`.

> Atenção: em hospedagens com filesystem efêmero, como Streamlit Community Cloud, alterações gravadas neste SQLite podem ser perdidas após reinicialização/redeploy. Para uso persistente em produção, migrar o banco para PostgreSQL ou outro banco remoto.
