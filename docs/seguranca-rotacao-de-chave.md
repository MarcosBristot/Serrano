# Rotação da chave `service_role` do Supabase (urgente)

O commit `49fc79b` (`scripts/import_boundaries.py`) gravou uma chave `service_role` como valor padrão
no código, e a branch já está no remoto. Essa chave ignora RLS (acesso total de leitura/escrita).

1. **Rotacione agora**: Supabase > Project Settings > API > gerar novo JWT secret / nova `service_role`.
   Atualize `.env` local e as variáveis do Render/Railway. Remover do código **não** invalida a chave.
2. Revise `Authentication > Users` e os logs por acessos inesperados.
3. Opcional, depois de rotacionar: remover do histórico com `git filter-repo --replace-text` e
   `git push --force` (combine com o time: reescreve o histórico).
4. Nunca coloque segredo como valor padrão de `os.getenv`. Use `.env.example` (sem valores).
