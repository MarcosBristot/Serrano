# Checklist do piloto

## Antes

- [ ] Chave `service_role` antiga rotacionada (`docs/seguranca-rotacao-de-chave.md`)
- [ ] Projeto Supabase **Pro** de produção (sa-east-1) e de staging; migrations aplicadas pelo CI
- [ ] `campero_backend` com senha; limite de arquivo do Storage ≥ 1 GB
- [ ] Railway `api` + `worker` em staging; `/ready` ok; latência medida (ver `docs/deploy.md`)
- [ ] SMTP com SPF/DKIM no domínio; `POST /destinos-notificacao/{id}/teste` chegando
- [ ] Frontend apontando para `/api/v1` (upload aceita `file` e `arquivo`)
- [ ] Ensaio completo em staging com o pendrive de teste: upload do zip, talhões importados,
      KPIs batem com `scripts/regressao_dump.py`
- [ ] Contrato/consentimento LGPD com o produtor do piloto
- [ ] Preço do diesel da nota cadastrado (`POST /precos-combustivel`); padrão é ANP S10 R$ 6,59/L

## Com o produtor

- [ ] Criar a organização, convidar o gestor (`POST /convites`)
- [ ] Upload do pendrive inteiro (zip) — o cadastro do monitor (talhões) é importado sozinho
- [ ] Desenhar/enviar contorno dos talhões sem contorno (localização por GPS depende disso)
- [ ] Conferir com o gestor: horas, litros, área e L/ha de 2 ou 3 dias que ele conhece
- [ ] Ajustar limiares (`PUT /config/regras`) e destinos de alerta

## Limites conhecidos (explicar ao produtor)

- Área: sem o sinal de implemento levantado, cabeceiras e estrada com motor ligado entram na área.
- Um trator, um firmware validados (JD Gen4 10.30). Outras marcas: próximo passo (ISOXML).
- ~65% dos arquivos do pendrive são vazios (normal) e muitas sessões são fragmentos de segundos.
