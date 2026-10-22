"""Exportação assíncrona (CSV/XLSX no Storage, link assinado) e relatório de qualidade."""

from __future__ import annotations

import io
import tempfile
from datetime import UTC, date, datetime, timedelta
from typing import Any, BinaryIO, Protocol, cast
from uuid import UUID

from sistemacampero.domain.errors import Invalido
from sistemacampero.domain.ingestao import BUCKET_EXPORTACOES, Job, TipoJob
from sistemacampero.domain.ports import Armazenamento, RepositorioIngestao

TIPOS = ("sessoes", "diarias", "alertas", "telemetria")
FORMATOS = ("csv", "xlsx")
DIAS_VALIDADE = 7
URL_EXPIRA_S = 3600

# Explicação para o gestor de cada motivo/problema (o frontend mostra ao lado do número).
EXPLICACOES: dict[str, str] = {
    "sem_canais_do_trator": "O monitor abriu o arquivo mas não gravou dado do trator "
    "(ligar/desligar o monitor sem operar). Normal: cerca de 2 em cada 3 arquivos do pendrive.",
    "sem_blocos_de_dados": "Arquivo só com cabeçalho, sem nenhum bloco de dados.",
    "sem_horario_de_inicio": "Cabeçalho sem horário de início: arquivo incompleto.",
    "ARQUIVO_INVALIDO": "Arquivo corrompido ou truncado (cópia interrompida do pendrive?).",
    "PLANO_LIMITE_MAQUINAS": "Máquina nova acima do limite do plano: o arquivo é processado "
    "quando houver vaga.",
    "MAQUINA_INATIVA": "Máquina desativada no cadastro.",
    "SESSAO_CURTA": "Fragmento de menos de 2 minutos: entra nos totais, não em médias.",
    "SEM_GPS": "Motor ligado sem nenhuma posição: sem talhão nem área por cobertura. "
    "Verificar receptor/sinal GPS do monitor.",
    "GPS_PARCIAL": "Parte do tempo sem posição: área por cobertura subestimada.",
    "CANAIS_AUSENTES": "Faltam canais do trator (ex.: RPM, vazão); algumas métricas ficam vazias.",
    "LACUNA_DE_DADOS": "Trecho longo sem nenhuma medida (falha de gravação do monitor).",
    "MUITOS_DESCARTES": "Muitos valores fisicamente impossíveis descartados na limpeza.",
    "HORIMETRO_DIVERGE": "Horímetro e tempo de motor ligado não batem: horas e consumo da "
    "sessão não são confiáveis.",
    "CONTADOR_DIVERGE": "Contador de combustível e vazão integrada não batem: lacuna de dados "
    "ou sensor.",
    "VARIOS_TALHOES": "A sessão passou por mais de um talhão ou por áreas sem contorno.",
}


class RepositorioExportacoes(Protocol):
    def criar(
        self, org: UUID, usuario: UUID | None, tipo: str, formato: str, filtros: dict[str, Any]
    ) -> UUID: ...
    def obter(self, org: UUID, ident: UUID) -> dict[str, Any]: ...
    def marcar(self, org: UUID, ident: UUID, **campos: Any) -> None: ...
    def csv_stream(
        self, org: UUID, tipo: str, f: dict[str, Any], versao: str, excel_br: bool = True
    ) -> Any: ...
    def xlsx(self, org: UUID, tipo: str, f: dict[str, Any], versao: str, destino: Any) -> int: ...
    def vencidas(self, limite: int = 100) -> list[dict[str, Any]]: ...
    def relatorio_qualidade(
        self, org: UUID, inicio: date | None, fim: date | None
    ) -> dict[str, Any]: ...


def _filtros_json(f: dict[str, Any]) -> dict[str, Any]:
    return {k: (str(v) if v is not None else None) for k, v in f.items()}


def _filtros_de(json_: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in json_.items():
        if v is None:
            continue
        out[k] = date.fromisoformat(v) if k in ("inicio", "fim") else UUID(v)
    return out


class ServicoExportacao:
    def __init__(
        self,
        repo: RepositorioExportacoes,
        ingestao: RepositorioIngestao,
        storage: Armazenamento,
        versao_metricas: str,
    ) -> None:
        self._repo = repo
        self._ingestao = ingestao
        self._storage = storage
        self._versao = versao_metricas

    def validar(self, tipo: str, formato: str, f: dict[str, Any]) -> None:
        if tipo not in TIPOS:
            raise Invalido("Tipo: sessoes, diarias, alertas ou telemetria.", codigo="TIPO_INVALIDO")
        if formato not in FORMATOS:
            raise Invalido("Formato: csv ou xlsx.", codigo="FORMATO_INVALIDO")
        if f.get("inicio") and f.get("fim") and f["fim"] < f["inicio"]:
            raise Invalido("'fim' antes de 'inicio'.", codigo="PERIODO_INVALIDO")
        if tipo == "telemetria" and not (f.get("inicio") and f.get("fim")):
            raise Invalido("Telemetria exige 'inicio' e 'fim'.", codigo="PERIODO_INVALIDO")

    def csv(self, org: UUID, tipo: str, f: dict[str, Any], excel_br: bool) -> Any:
        self.validar(tipo, "csv", f)
        return self._repo.csv_stream(org, tipo, f, self._versao, excel_br)

    def solicitar(
        self, org: UUID, usuario: UUID | None, tipo: str, formato: str, f: dict[str, Any]
    ) -> UUID:
        self.validar(tipo, formato, f)
        ident = self._repo.criar(org, usuario, tipo, formato, _filtros_json(f))
        self._ingestao.enfileirar(
            org, TipoJob.EXPORTAR, {"exportacao_id": str(ident)}, chave=f"exportar:{ident}"
        )
        return ident

    def situacao(self, org: UUID, ident: UUID) -> dict[str, Any]:
        e = self._repo.obter(org, ident)
        url = None
        if e["status"] == "concluida" and e["caminho_storage"]:
            url = self._storage.url_assinada(BUCKET_EXPORTACOES, e["caminho_storage"], URL_EXPIRA_S)
        return {**e, "url": url}

    def executar(self, job: Job, controle: Any) -> dict[str, Any]:
        org, ident = job.organizacao_id, UUID(job.payload["exportacao_id"])
        e = self._repo.obter(org, ident)
        self._repo.marcar(org, ident, status="executando")
        f = _filtros_de(e["filtros"])
        caminho = f"{org}/{ident}.{e['formato']}"
        try:
            with tempfile.TemporaryFile() as arquivo_tmp:
                tmp = cast(BinaryIO, arquivo_tmp)
                if e["formato"] == "xlsx":
                    linhas = self._repo.xlsx(org, e["tipo"], f, self._versao, tmp)
                else:
                    linhas = -1  # cabeçalho
                    for parte in self._repo.csv_stream(org, e["tipo"], f, self._versao):
                        tmp.write(parte)
                        linhas += parte.count(b"\n")
                    controle.verificar()
                tmp.seek(0)
                tipo_mime = (
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    if e["formato"] == "xlsx"
                    else "text/csv"
                )
                self._storage.gravar(BUCKET_EXPORTACOES, caminho, tmp, tipo_mime)
        except Invalido as exc:
            self._repo.marcar(org, ident, status="erro", erro=f"{exc.codigo}: {exc.mensagem}")
            return {"status": "erro", "motivo": exc.codigo}
        self._repo.marcar(
            org,
            ident,
            status="concluida",
            caminho_storage=caminho,
            linhas=max(linhas, 0),
            expira_em=datetime.now(UTC) + timedelta(days=DIAS_VALIDADE),
        )
        return {"status": "concluida", "linhas": max(linhas, 0)}

    def limpar_vencidas(self) -> int:
        vencidas = self._repo.vencidas()
        for e in vencidas:
            if e["caminho_storage"]:
                self._storage.apagar(BUCKET_EXPORTACOES, e["caminho_storage"])
            self._repo.marcar(e["organizacao_id"], e["id"], status="expirada", caminho_storage=None)
        return len(vencidas)

    def relatorio_qualidade(
        self, org: UUID, inicio: date | None, fim: date | None
    ) -> dict[str, Any]:
        r = self._repo.relatorio_qualidade(org, inicio, fim)
        for a in r["arquivos"]:
            a["explicacao"] = EXPLICACOES.get(a["motivo"]) or EXPLICACOES.get(a["status"])
        for p in r["problemas"]:
            p["explicacao"] = EXPLICACOES.get(p["codigo"])
        return r


__all__ = ["EXPLICACOES", "ServicoExportacao", "io"]
