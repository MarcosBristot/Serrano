# 🚜 Campero Sistemas
 
> **Fim da cegueira multimarca no campo.** Uma plataforma SaaS de gestão de frotas agrícolas que unifica dados de telemetria de diferentes fabricantes, gerando insights operacionais claros e acionáveis para o produtor rural.
 
## 📌 Sobre o Projeto
 
Produtores rurais frequentemente operam frotas mistas (John Deere, CNH, AGCO, etc.). Cada marca possui seu próprio ecossistema fechado de dados, dificultando a visão global da operação. A **Campero Sistemas** resolve esse problema através de um motor de ingestão de arquivos padronizados (pendrives), unificando a leitura de horímetros, consumo de combustível e tempo de ociosidade em um único painel.
 
**Local de Operação Inicial:** Passo Fundo e região (RS).
 
## 🚀 Principais Funcionalidades (MVP)
 
* **Ingestão Universal:** Leitura (parser) de arquivos brutos (CSV/XML) extraídos via pendrive das cabines dos tratores.
* **Mapeamento Geoespacial:** Rastreamento de rotas e áreas trabalhadas utilizando banco de dados com suporte espacial.
* **Análise de Consumo:** Cálculo automático de métricas vitais como *Litros/Horímetro* e *Litros/Hectare*.
* **Alertas Inteligentes (IA):** Detecção automática de anomalias, como desperdício de combustível por tempo excessivo de motor ocioso (IDLE).
## 🛠️ Stack Tecnológico
 
* **Frontend:** Web App Responsivo para interface de visualização e upload de arquivos.
* **Backend:** API REST para processamento da regra de negócio e ingestão de dados.
* **Banco de Dados:** PostgreSQL com extensão **PostGIS** para armazenamento e consulta de dados geoespaciais.
* **Inteligência:** Módulo de IA / Scripts de análise para detecção de anomalias de consumo.
## 👥 Equipe e Papéis
 
* **Marcos:** Liderança / Estruturação de Negócios e Legal.
* **Charles:** Vendas / Validação de Mercado e Operação Pendrive.
* **João:** Frontend / UI-UX Design.
* **Raul:** Backend / Arquitetura PostGIS e APIs.
* **Guilherme:** Backend / IA, Parser de Arquivos e Métricas.
## 💻 Como Rodar o Projeto Localmente
 
### 1. Pré-requisitos
 
* Git instalado em sua máquina.
* Node.js, Python ou ambiente da linguagem definida pela equipe.
* PostgreSQL + PostGIS em execução (local ou via Docker).
### 2. Passos para Instalação e Execução
 
Todo o projeto (Frontend e Backend) é executado a partir do diretório principal.
 
```bash
# Clone o repositório para a sua máquina
git clone https://github.com/MarcosBristot/SistemaCampero
 
# Entre na pasta raiz do projeto
cd campero-sistemas
 
```
 
## 🛡️ Padrão de Contribuição e Git Flow
 
Para manter a estabilidade do código e a organização do histórico, utilizamos regras estritas de versionamento. A branch `master` (ou `main`) é protegida e não aceita commits diretos.
 
### 1. Nomenclatura de Branches
 
Crie a sua branch a partir da principal utilizando prefixos que indicam a natureza do trabalho:
 
* `feat/` - Para novas funcionalidades (ex: `feat/upload-pendrive`)
* `fix/` - Para correção de bugs (ex: `fix/calculo-consumo`)
* `docs/` - Para documentação (ex: `docs/acordo-societario`)
* `refactor/` - Para refatoração de código existente
### 2. Padrão de Commits (Conventional Commits)
 
Suas mensagens de commit devem ser claras, curtas e seguir o padrão:
 
* `feat: adiciona componente de grafico em barra`
* `fix: corrige erro de leitura da coluna speed_kmh`
* `docs: atualiza readme com instrucoes de banco de dados`
### 3. Passo a Passo do Fluxo
 
1. Atualize sua base local: `git checkout master` e `git pull`
2. Crie sua branch: `git checkout -b tipo/sua-tarefa`
3. Faça suas alterações, adicione-as (`git add .`) e "commite" (`git commit -m "tipo: mensagem"`)
4. Envie para o repositório remoto: `git push origin tipo/sua-tarefa`
5. Abra um Pull Request (PR) no GitHub, referenciando o link do cartão no Trello.
6. Aguarde a revisão (Code Review) e aprovação (Approve) de pelo menos 1 membro da equipe antes do Merge.
 
### 4. Setup do projeto — uv

Este projeto usa **[uv](https://docs.astral.sh/uv/)** para gerenciar o ambiente virtual e as dependências. Este guia explica como instalar e usar a ferramenta.

## 1. Instalando o uv

Escolha o comando de acordo com o seu sistema operacional:

```bash
# Linux / macOS
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# Alternativa via pip (qualquer SO, se já tiver Python instalado)
pip install uv
```

Verifique a instalação:

```bash
uv --version
```

## 2. Clonando e configurando o projeto

```bash
git clone https://github.com/MarcosBristot/SistemaCampero
cd SistemaCampero

# Cria o ambiente virtual e instala todas as dependências
# (baseado no pyproject.toml + uv.lock)
uv sync
```

O `uv sync` cria uma pasta `.venv/` local com o ambiente virtual e instala exatamente as versões travadas no `uv.lock`. Isso garante que todos no time usem as mesmas versões de bibliotecas.

Para rodar qualquer comando/script dentro desse ambiente, use `uv run`:

```bash
uv run python meu_script.py
```

### Adicionando uma nova dependência

```bash
uv add nome-do-pacote          # dependência normal
```

Isso atualiza automaticamente o `pyproject.toml` e o `uv.lock`. **Sempre commite o `uv.lock`** junto com as mudanças, para manter o ambiente reprodutível para todo o time.

## 3. Resumo rápido para quem está entrando no projeto agora

```bash
git clone https://github.com/MarcosBristot/SistemaCampero
cd SistemaCampero
uv sync
```

Pronto — ambiente configurado e pronto para rodar o projeto.