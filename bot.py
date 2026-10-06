import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

import os
import sqlite3
import asyncio
from datetime import datetime

# ============================================================
# CONFIGURAÇÕES
# ============================================================

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")

GUILD_ID = 1541410785765359646

# CARGOS
CARGO_INICIAR_SERVICO = 1541925558571638895
CARGO_RH = 1544156012783870002
CARGO_ADMIN = 1544156012783870002
CARGO_AUSENCIA = 1551724465405169784
CARGO_SUPERIOR = 1544156012783870002

CARGO_ADV1 = 1549913924109869136
CARGO_ADV2 = 1549914033921065064
CARGO_ADV3 = 1549914116045545482
CARGO_ADV_VERBAL = 1549914190381064303

CARGOS_ADVERTENCIA = {
    "ADV1": CARGO_ADV1,
    "ADV2": CARGO_ADV2,
    "ADV3": CARGO_ADV3,
    "ADV VERBAL": CARGO_ADV_VERBAL
}

# CANAIS
CANAL_PONTO = 1551393404812926976
CANAL_RH = 1551393253113200680
CANAL_SET = 1541412045025579109
CANAL_LOGS_GERAIS = 1551393710250528828
CANAL_APREENDIDOS = 1541928448887627886
CANAL_AUSENCIA = 1548105065695281233
CANAL_ADVERTENCIA = 1549913860956364981

# CATEGORIAS
CATEGORIA_QSV = 1542183103953371297
CATEGORIA_RH = 1541926623274864710


# ============================================================
# BANCO DE DADOS
# ============================================================

db = sqlite3.connect("prf_bot.db")
cursor = db.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS pontos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    nome TEXT,
    duracao INTEGER,
    inicio TEXT,
    fim TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS ausencias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    nome TEXT,
    id_cidade TEXT,
    motivo TEXT,
    data TEXT,
    tempo TEXT,
    criado_em TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS advertencias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    policial TEXT,
    user_id INTEGER,
    id_cidade TEXT,
    cargo TEXT,
    advertencia TEXT,
    motivo TEXT,
    aplicado_por TEXT,
    aplicado_por_id INTEGER,
    criado_em TEXT
)
""")

db.commit()


# ============================================================
# BOT
# ============================================================

intents = discord.Intents.default()
intents.members = True
intents.voice_states = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# ============================================================
# SERVIÇOS ATIVOS
# ============================================================

servicos = {}


# ============================================================
# FUNÇÕES
# ============================================================

def tem_cargo(member, cargo_id):
    return any(role.id == cargo_id for role in member.roles)


def formatar_tempo(segundos):
    segundos = int(segundos)

    horas = segundos // 3600
    minutos = (segundos % 3600) // 60
    segundos_restantes = segundos % 60

    return (
        f"{horas}h "
        f"{minutos}min "
        f"{segundos_restantes}s"
    )


def contar_linhas(texto):
    return len(
        [linha for linha in texto.splitlines() if linha.strip()]
    )


async def enviar_log(titulo, descricao, cor=discord.Color.red()):
    canal = bot.get_channel(CANAL_LOGS_GERAIS)

    if canal is None:
        return

    embed = discord.Embed(
        title=titulo,
        description=descricao,
        color=cor,
        timestamp=datetime.now()
    )

    embed.set_footer(text="PRF - BOT | Logs")

    await canal.send(embed=embed)


def registrar_tempo(user_id, nome, duracao, inicio, fim):
    cursor.execute(
        """
        INSERT INTO pontos
        (user_id, nome, duracao, inicio, fim)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            user_id,
            nome,
            int(duracao),
            inicio,
            fim
        )
    )

    db.commit()


# ============================================================
# ENTRAR NO SERVIÇO
# ============================================================

def entrar_servico(channel_id, member):

    servico = servicos.get(channel_id)

    if servico is None:
        return

    if member.id in servico["participantes"]:
        return

    servico["participantes"][member.id] = {
        "member": member,
        "inicio": datetime.now()
    }


# ============================================================
# SAIR DO SERVIÇO
# ============================================================

def sair_servico(channel_id, member):

    servico = servicos.get(channel_id)

    if servico is None:
        return

    participante = servico["participantes"].get(member.id)

    if participante is None:
        return

    agora = datetime.now()

    inicio = participante["inicio"]

    duracao = int(
        (agora - inicio).total_seconds()
    )

    servico["tempos"][member.id] = (
        servico["tempos"].get(member.id, 0)
        + duracao
    )

    servico["participantes"].pop(member.id, None)


# ============================================================
# ENCERRAR SERVIÇO
# ============================================================

async def encerrar_servico(channel_id):

    servico = servicos.get(channel_id)

    if servico is None:
        return

    agora = datetime.now()

    # Fecha os tempos de quem ainda está na call
    for user_id, participante in list(
        servico["participantes"].items()
    ):

        inicio = participante["inicio"]

        duracao = int(
            (agora - inicio).total_seconds()
        )

        servico["tempos"][user_id] = (
            servico["tempos"].get(user_id, 0)
            + duracao
        )

    # Salva todos
    for user_id, tempo in servico["tempos"].items():

        member = bot.get_user(user_id)

        nome = (
            member.display_name
            if member
            else str(user_id)
        )

        registrar_tempo(
            user_id,
            nome,
            tempo,
            servico["inicio"].isoformat(),
            agora.isoformat()
        )

    canal = bot.get_channel(channel_id)

    if canal:
        try:
            await canal.delete(
                reason="Serviço encerrado."
            )
        except Exception as erro:
            print(
                f"Erro ao apagar call: {erro}"
            )

    servicos.pop(channel_id, None)


# ============================================================
# MODAL INICIAR SERVIÇO
# ============================================================

class IniciarServicoModal(
    discord.ui.Modal,
    title="INICIAR SERVIÇO"
):

    modelo = discord.ui.TextInput(
        label="MODELO DA VTR",
        placeholder="Ex: TRAILBLAZER",
        required=True,
        max_length=50
    )

    prefixo = discord.ui.TextInput(
        label="PREFIXO",
        placeholder="Ex: M-123",
        required=True,
        max_length=30
    )

    async def on_submit(
        self,
        interaction: discord.Interaction
    ):

        if not tem_cargo(
            interaction.user,
            CARGO_INICIAR_SERVICO
        ):
            await interaction.response.send_message(
                "Você não possui o cargo necessário para iniciar serviço.",
                ephemeral=True
            )
            return

        guild = interaction.guild

        categoria = guild.get_channel(
            CATEGORIA_QSV
        )

        if categoria is None:
            await interaction.response.send_message(
                "Categoria de QSV não encontrada.",
                ephemeral=True
            )
            return

        nome_call = (
            f"{self.modelo.value.upper()} / "
            f"{self.prefixo.value.upper()}"
        )

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(
                view_channel=True,
                connect=True,
                speak=True
            )
        }

        overwrites[guild.me] = discord.PermissionOverwrite(
            view_channel=True,
            connect=True,
            speak=True,
            move_members=True,
            manage_channels=True
        )

        try:
            canal = await guild.create_voice_channel(
                name=nome_call,
                category=categoria,
                overwrites=overwrites,
                user_limit=4,
                reason="Início de serviço PRF"
            )
        except Exception as erro:
            await interaction.response.send_message(
                f"Erro ao criar a QSV: {erro}",
                ephemeral=True
            )
            return

        servicos[canal.id] = {
            "responsavel": interaction.user.id,
            "inicio": datetime.now(),
            "modelo": self.modelo.value,
            "prefixo": self.prefixo.value,
            "participantes": {},
            "tempos": {}
        }

        try:
            await interaction.user.move_to(canal)
        except Exception:
            pass

        entrar_servico(
            canal.id,
            interaction.user
        )

        await interaction.response.send_message(
            f"Serviço iniciado!\n"
            f"QSV: {canal.mention}",
            ephemeral=True
        )

        await enviar_log(
            "SERVIÇO INICIADO",
            f"Responsável: {interaction.user.mention}\n"
            f"Viatura: {self.modelo.value.upper()} / "
            f"{self.prefixo.value.upper()}",
            discord.Color.green()
        )


# ============================================================
# MODAL ENCERRAR SERVIÇO
# ============================================================

class EncerrarServicoModal(
    discord.ui.Modal,
    title="ENCERRAR SERVIÇO"
):

    prefixo = discord.ui.TextInput(
        label="PREFIXO DA VTR",
        placeholder="Ex: M-123",
        required=True,
        max_length=30
    )

    async def on_submit(
        self,
        interaction: discord.Interaction
    ):

        canal_encontrado = None
        servico_encontrado = None

        for channel_id, servico in servicos.items():

            if (
                servico["responsavel"]
                == interaction.user.id
            ):

                canal_encontrado = channel_id
                servico_encontrado = servico
                break

        if canal_encontrado is None:
            await interaction.response.send_message(
                "Você não possui um serviço ativo.",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            "Serviço encerrado. A QSV será removida.",
            ephemeral=True
        )

        await enviar_log(
            "SERVIÇO ENCERRADO",
            f"Responsável: {interaction.user.mention}\n"
            f"Prefixo: {self.prefixo.value.upper()}",
            discord.Color.red()
        )

        await encerrar_servico(
            canal_encontrado
        )


# ============================================================
# VIEW DO PONTO
# ============================================================

class PontoView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="INICIAR SERVIÇO",
        style=discord.ButtonStyle.success,
        custom_id="prf_iniciar_servico"
    )
    async def iniciar(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        if not tem_cargo(
            interaction.user,
            CARGO_INICIAR_SERVICO
        ):
            await interaction.response.send_message(
                "Você não possui permissão para iniciar serviço.",
                ephemeral=True
            )
            return

        await interaction.response.send_modal(
            IniciarServicoModal()
        )

    @discord.ui.button(
        label="ENCERRAR SERVIÇO",
        style=discord.ButtonStyle.danger,
        custom_id="prf_encerrar_servico"
    )
    async def encerrar(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        await interaction.response.send_modal(
            EncerrarServicoModal()
        )


# ============================================================
# RH
# ============================================================

class FecharTicketRHView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="FECHAR TICKET",
        style=discord.ButtonStyle.danger,
        custom_id="prf_fechar_rh"
    )
    async def fechar(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        if not tem_cargo(
            interaction.user,
            CARGO_RH
        ):
            await interaction.response.send_message(
                "Somente o RH pode fechar este ticket.",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            "Ticket será fechado em 5 segundos.",
            ephemeral=False
        )

        await asyncio.sleep(5)

        try:
            await interaction.channel.delete(
                reason="Ticket RH fechado."
            )
        except Exception:
            pass


class RHView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="ABRIR ATENDIMENTO RH",
        style=discord.ButtonStyle.primary,
        custom_id="prf_abrir_rh"
    )
    async def abrir(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        guild = interaction.guild

        categoria = guild.get_channel(
            CATEGORIA_RH
        )

        if categoria is None:
            await interaction.response.send_message(
                "Categoria do RH não encontrada.",
                ephemeral=True
            )
            return

        nome = (
            f"rh-{interaction.user.id}"
        )

        for canal in categoria.channels:
            if canal.name == nome:
                await interaction.response.send_message(
                    "Você já possui um ticket do RH aberto.",
                    ephemeral=True
                )
                return

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(
                view_channel=False
            ),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True
            )
        }

        cargo_rh = guild.get_role(
            CARGO_RH
        )

        if cargo_rh:
            overwrites[cargo_rh] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_channels=True
            )

        canal = await guild.create_text_channel(
            name=nome,
            category=categoria,
            overwrites=overwrites,
            reason="Ticket RH"
        )

        embed = discord.Embed(
            title="ATENDIMENTO RH",
            description=(
                f"{interaction.user.mention}, seu atendimento foi aberto.\n\n"
                "Aguarde um membro do RH."
            ),
            color=discord.Color.red()
        )

        await canal.send(
            content=interaction.user.mention,
            embed=embed,
            view=FecharTicketRHView()
        )

        await interaction.response.send_message(
            f"Seu ticket foi criado: {canal.mention}",
            ephemeral=True
        )


# ============================================================
# SET
# ============================================================

class SETModal(
    discord.ui.Modal,
    title="SOLICITAÇÃO DE SET"
):

    nome = discord.ui.TextInput(
        label="Nome",
        required=True,
        max_length=100
    )

    id_cidade = discord.ui.TextInput(
        label="ID DA CIDADE",
        required=True,
        max_length=50
    )

    cargo_desejado = discord.ui.TextInput(
        label="Cargo desejado",
        required=True,
        max_length=100
    )

    motivo = discord.ui.TextInput(
        label="Motivo",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=1500
    )

    async def on_submit(
        self,
        interaction: discord.Interaction
    ):

        embed = discord.Embed(
            title="SOLICITAÇÃO DE SET",
            color=discord.Color.red(),
            timestamp=datetime.now()
        )

        embed.add_field(
            name="Nome",
            value=self.nome.value,
            inline=False
        )

        embed.add_field(
            name="ID DA CIDADE",
            value=self.id_cidade.value,
            inline=True
        )

        embed.add_field(
            name="Cargo desejado",
            value=self.cargo_desejado.value,
            inline=True
        )

        embed.add_field(
            name="Motivo",
            value=self.motivo.value,
            inline=False
        )

        embed.add_field(
            name="Solicitado por",
            value=interaction.user.mention,
            inline=False
        )

        embed.set_footer(
            text="PRF - BOT | Solicitação de SET"
        )

        await enviar_log(
            "NOVA SOLICITAÇÃO DE SET",
            f"Nome: {self.nome.value}\n"
            f"ID da cidade: {self.id_cidade.value}\n"
            f"Cargo desejado: {self.cargo_desejado.value}\n"
            f"Motivo: {self.motivo.value}\n"
            f"Solicitado por: {interaction.user.mention}",
            discord.Color.red()
        )

        canal = interaction.guild.get_channel(
            CANAL_LOGS_GERAIS
        )

        if canal:
            await canal.send(embed=embed)

        await interaction.response.send_message(
            "Sua solicitação de SET foi enviada.",
            ephemeral=True
        )


class SETView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="PEDIR SET",
        style=discord.ButtonStyle.primary,
        custom_id="prf_pedir_set"
    )
    async def pedir(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await interaction.response.send_modal(
            SETModal()
        )


# ============================================================
# AUSÊNCIA
# ============================================================

class AusenciaModal(
    discord.ui.Modal,
    title="REGISTRAR AUSÊNCIA"
):

    nome = discord.ui.TextInput(
        label="Nome",
        required=True,
        max_length=100
    )

    id_cidade = discord.ui.TextInput(
        label="ID DA CIDADE",
        required=True,
        max_length=50
    )

    motivo = discord.ui.TextInput(
        label="Motivo",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=1000
    )

    data = discord.ui.TextInput(
        label="Data",
        placeholder="Ex: 22/09/2026",
        required=True,
        max_length=30
    )

    tempo = discord.ui.TextInput(
        label="Tempo de ausência",
        placeholder="Ex: 7 dias",
        required=True,
        max_length=50
    )

    async def on_submit(
        self,
        interaction: discord.Interaction
    ):

        agora = datetime.now()

        cursor.execute(
            """
            INSERT INTO ausencias
            (user_id, nome, id_cidade, motivo, data, tempo, criado_em)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                interaction.user.id,
                self.nome.value,
                self.id_cidade.value,
                self.motivo.value,
                self.data.value,
                self.tempo.value,
                agora.isoformat()
            )
        )

        db.commit()

        cargo = interaction.guild.get_role(
            CARGO_AUSENCIA
        )

        if cargo:
            try:
                await interaction.user.add_roles(
                    cargo,
                    reason="Registro de ausência"
                )
            except discord.Forbidden:
                await interaction.response.send_message(
                    "A ausência foi registrada, mas não consegui dar o cargo. "
                    "Verifique a hierarquia de cargos.",
                    ephemeral=True
                )
                return

        canal = interaction.guild.get_channel(
            CANAL_AUSENCIA
        )

        embed = discord.Embed(
            title="REGISTRO DE AUSÊNCIA",
            color=discord.Color.orange(),
            timestamp=agora
        )

        embed.add_field(
            name="Nome",
            value=self.nome.value,
            inline=False
        )

        embed.add_field(
            name="ID DA CIDADE",
            value=self.id_cidade.value,
            inline=True
        )

        embed.add_field(
            name="Motivo",
            value=self.motivo.value,
            inline=False
        )

        embed.add_field(
            name="Data",
            value=self.data.value,
            inline=True
        )

        embed.add_field(
            name="Tempo de ausência",
            value=self.tempo.value,
            inline=True
        )

        embed.add_field(
            name="Registrado por",
            value=interaction.user.mention,
            inline=False
        )

        if canal:
            await canal.send(embed=embed)

        await interaction.response.send_message(
            "Ausência registrada e cargo de ausência atribuído.",
            ephemeral=True
        )


class AusenciaView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="REGISTRAR AUSÊNCIA",
        style=discord.ButtonStyle.secondary,
        custom_id="prf_registrar_ausencia"
    )
    async def registrar(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await interaction.response.send_modal(
            AusenciaModal()
        )


# ============================================================
# APREENSÕES
# ============================================================

class ApreensaoModal1(
    discord.ui.Modal,
    title="REGISTRO DE APREENSÃO - PARTE 1"
):

    artigo = discord.ui.TextInput(
        label="Artigo",
        placeholder="Informe o artigo.",
        required=True,
        max_length=200
    )

    policiais = discord.ui.TextInput(
        label="Policiais envolvidos",
        placeholder="Informe os policiais envolvidos.",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=1000
    )

    suspeito = discord.ui.TextInput(
        label="Nome do suspeito",
        required=True,
        max_length=100
    )

    rg = discord.ui.TextInput(
        label="RG do suspeito",
        required=True,
        max_length=100
    )

    descricao = discord.ui.TextInput(
        label="Descrição - mínimo 4 linhas",
        placeholder="Descreva a ocorrência em pelo menos 4 linhas.",
        style=discord.TextStyle.paragraph,
        required=True,
        min_length=20,
        max_length=4000
    )

    async def on_submit(
        self,
        interaction: discord.Interaction
    ):

        if contar_linhas(self.descricao.value) < 4:
            await interaction.response.send_message(
                "A descrição precisa ter no mínimo 4 linhas.",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            "Primeira parte registrada. Clique em CONTINUAR.",
            ephemeral=True,
            view=ApreensaoContinuacaoView(
                artigo=self.artigo.value,
                policiais=self.policiais.value,
                suspeito=self.suspeito.value,
                rg=self.rg.value,
                descricao=self.descricao.value
            )
        )


class ApreensaoModal2(
    discord.ui.Modal,
    title="REGISTRO DE APREENSÃO - PARTE 2"
):

    def __init__(
        self,
        artigo,
        policiais,
        suspeito,
        rg,
        descricao
    ):
        super().__init__()

        self.artigo_valor = artigo
        self.policiais_valor = policiais
        self.suspeito_valor = suspeito
        self.rg_valor = rg
        self.descricao_valor = descricao

    itens = discord.ui.TextInput(
        label="Itens apreendidos",
        placeholder="Informe os itens apreendidos.",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=2000
    )

    veiculos = discord.ui.TextInput(
        label="Veículos apreendidos",
        placeholder="Se não houver, escreva Nenhum.",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=2000
    )

    async def on_submit(
        self,
        interaction: discord.Interaction
    ):

        canal = interaction.guild.get_channel(
            CANAL_APREENDIDOS
        )

        if canal is None:
            await interaction.response.send_message(
                "Canal de apreendidos não encontrado.",
                ephemeral=True
            )
            return

        agora = datetime.now()

        embed = discord.Embed(
            title="REGISTRO DE APREENSÃO",
            color=discord.Color.red(),
            timestamp=agora
        )

        embed.add_field(
            name="Artigo",
            value=self.artigo_valor,
            inline=False
        )

        embed.add_field(
            name="Policiais envolvidos",
            value=self.policiais_valor,
            inline=False
        )

        embed.add_field(
            name="Nome do suspeito",
            value=self.suspeito_valor,
            inline=True
        )

        embed.add_field(
            name="RG do suspeito",
            value=self.rg_valor,
            inline=True
        )

        embed.add_field(
            name="Itens apreendidos",
            value=self.itens.value,
            inline=False
        )

        embed.add_field(
            name="Veículos apreendidos",
            value=self.veiculos.value,
            inline=False
        )

        embed.add_field(
            name="Descrição da ocorrência",
            value=self.descricao_valor,
            inline=False
        )

        embed.add_field(
            name="Registrado por",
            value=interaction.user.mention,
            inline=False
        )

        embed.set_footer(
            text="PRF - BOT | Registro de Apreensões"
        )

        await canal.send(
            embed=embed
        )

        await interaction.response.send_message(
            "Registro de apreensão enviado com sucesso.",
            ephemeral=True
        )

        await enviar_log(
            "NOVA APREENSÃO REGISTRADA",
            f"Suspeito: {self.suspeito_valor}\n"
            f"RG: {self.rg_valor}\n"
            f"Artigo: {self.artigo_valor}\n"
            f"Registrado por: {interaction.user.mention}",
            discord.Color.red()
        )


class ApreensaoContinuacaoView(
    discord.ui.View
):

    def __init__(
        self,
        artigo,
        policiais,
        suspeito,
        rg,
        descricao
    ):
        super().__init__(timeout=120)

        self.artigo = artigo
        self.policiais = policiais
        self.suspeito = suspeito
        self.rg = rg
        self.descricao = descricao

    @discord.ui.button(
        label="CONTINUAR",
        style=discord.ButtonStyle.primary
    )
    async def continuar(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        await interaction.response.send_modal(
            ApreensaoModal2(
                artigo=self.artigo,
                policiais=self.policiais,
                suspeito=self.suspeito,
                rg=self.rg,
                descricao=self.descricao
            )
        )


class ApreensaoView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="REGISTRAR APREENSÃO",
        style=discord.ButtonStyle.danger,
        custom_id="prf_registrar_apreensao"
    )
    async def registrar(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await interaction.response.send_modal(
            ApreensaoModal1()
        )


# ============================================================
# ADVERTÊNCIAS
# ============================================================

class AdvertenciaTipoView(discord.ui.View):

    def __init__(self, policial):
        super().__init__(timeout=120)
        self.policial = policial

    @discord.ui.button(
        label="ADV1",
        style=discord.ButtonStyle.danger
    )
    async def adv1(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await interaction.response.send_modal(
            AdvertenciaModal(
                self.policial,
                "ADV1"
            )
        )

    @discord.ui.button(
        label="ADV2",
        style=discord.ButtonStyle.danger
    )
    async def adv2(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await interaction.response.send_modal(
            AdvertenciaModal(
                self.policial,
                "ADV2"
            )
        )

    @discord.ui.button(
        label="ADV3",
        style=discord.ButtonStyle.danger
    )
    async def adv3(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await interaction.response.send_modal(
            AdvertenciaModal(
                self.policial,
                "ADV3"
            )
        )

    @discord.ui.button(
        label="ADV VERBAL",
        style=discord.ButtonStyle.secondary
    )
    async def adv_verbal(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await interaction.response.send_modal(
            AdvertenciaModal(
                self.policial,
                "ADV VERBAL"
            )
        )


class SelecionarPolicialView(
    discord.ui.View
):

    def __init__(self):
        super().__init__(timeout=120)

    @discord.ui.select(
        cls=discord.ui.UserSelect,
        placeholder="Selecione o policial",
        min_values=1,
        max_values=1
    )
    async def selecionar(
        self,
        interaction: discord.Interaction,
        select: discord.ui.UserSelect
    ):

        if not tem_cargo(
            interaction.user,
            CARGO_SUPERIOR
        ):
            await interaction.response.send_message(
                "Somente superiores podem aplicar advertências.",
                ephemeral=True
            )
            return

        policial = select.values[0]

        await interaction.response.send_message(
            f"Policial selecionado: {policial.mention}\n\n"
            "Agora escolha o tipo de advertência:",
            ephemeral=True,
            view=AdvertenciaTipoView(policial)
        )


class AdvertenciaModal(
    discord.ui.Modal,
    title="APLICAR ADVERTÊNCIA"
):

    def __init__(
        self,
        policial: discord.Member,
        tipo: str
    ):
        super().__init__()

        self.policial = policial
        self.tipo = tipo

    id_cidade = discord.ui.TextInput(
        label="ID DA CIDADE",
        placeholder="ID da cidade do policial.",
        required=True,
        max_length=50
    )

    cargo = discord.ui.TextInput(
        label="Cargo",
        placeholder="Cargo atual do policial.",
        required=True,
        max_length=100
    )

    motivo = discord.ui.TextInput(
        label="Motivo",
        placeholder="Motivo da advertência.",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=1500
    )

    async def on_submit(
        self,
        interaction: discord.Interaction
    ):

        superior = interaction.user

        if not tem_cargo(
            superior,
            CARGO_SUPERIOR
        ):
            await interaction.response.send_message(
                "Você não possui autorização para aplicar advertências.",
                ephemeral=True
            )
            return

        cargo_id = CARGOS_ADVERTENCIA[
            self.tipo
        ]

        cargo_adv = interaction.guild.get_role(
            cargo_id
        )

        if cargo_adv is None:
            await interaction.response.send_message(
                f"O cargo {self.tipo} não foi encontrado.",
                ephemeral=True
            )
            return

        try:
            await self.policial.add_roles(
                cargo_adv,
                reason=(
                    f"{self.tipo} aplicada por "
                    f"{superior}"
                )
            )

        except discord.Forbidden:
            await interaction.response.send_message(
                "Não consegui atribuir o cargo da advertência. "
                "Coloque o cargo do BOT acima dos cargos ADV "
                "na hierarquia do servidor.",
                ephemeral=True
            )
            return

        except Exception as erro:
            print(
                f"Erro ao atribuir advertência: {erro}"
            )

            await interaction.response.send_message(
                "Não consegui atribuir o cargo.",
                ephemeral=True
            )
            return

        canal = interaction.guild.get_channel(
            CANAL_ADVERTENCIA
        )

        agora = datetime.now()

        cursor.execute(
            """
            INSERT INTO advertencias
            (policial, user_id, id_cidade, cargo, advertencia,
             motivo, aplicado_por, aplicado_por_id, criado_em)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self.policial.display_name,
                self.policial.id,
                self.id_cidade.value,
                self.cargo.value,
                self.tipo,
                self.motivo.value,
                str(superior),
                superior.id,
                agora.isoformat()
            )
        )

        db.commit()

        embed = discord.Embed(
            title="ADVERTÊNCIA",
            color=discord.Color.orange(),
            timestamp=agora
        )

        embed.description = (
            "A: Polícia Rodoviária Federal"
        )

        embed.add_field(
            name="Nome",
            value=self.policial.mention,
            inline=False
        )

        embed.add_field(
            name="ID DA CIDADE",
            value=self.id_cidade.value,
            inline=True
        )

        embed.add_field(
            name="Cargo",
            value=self.cargo.value,
            inline=True
        )

        embed.add_field(
            name="Advertência",
            value=self.tipo,
            inline=True
        )

        embed.add_field(
            name="Motivo",
            value=self.motivo.value,
            inline=False
        )

        embed.add_field(
            name="Aplicada por",
            value=superior.mention,
            inline=False
        )

        embed.set_footer(
            text="PRF - BOT | Sistema de Advertências"
        )

        if canal:
            await canal.send(
                embed=embed
            )

        await interaction.response.send_message(
            f"{self.tipo} aplicada com sucesso em "
            f"{self.policial.mention}.\n"
            "O cargo foi atribuído automaticamente.",
            ephemeral=True
        )

        await enviar_log(
            "ADVERTÊNCIA APLICADA",
            f"Policial: {self.policial.mention}\n"
            f"ID da cidade: {self.id_cidade.value}\n"
            f"Cargo: {self.cargo.value}\n"
            f"Advertência: {self.tipo}\n"
            f"Motivo: {self.motivo.value}\n"
            f"Aplicada por: {superior.mention}",
            discord.Color.orange()
        )


class AdvertenciaView(
    discord.ui.View
):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="APLICAR ADVERTÊNCIA",
        style=discord.ButtonStyle.danger,
        custom_id="prf_aplicar_advertencia"
    )
    async def aplicar(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        if not tem_cargo(
            interaction.user,
            CARGO_SUPERIOR
        ):
            await interaction.response.send_message(
                "Somente superiores podem aplicar advertências.",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            "Selecione o policial que receberá a advertência:",
            ephemeral=True,
            view=SelecionarPolicialView()
        )


# ============================================================
# COMANDO /MSG
# ============================================================

@bot.tree.command(
    name="msg",
    description="Envia uma mensagem com anexo opcional.",
    guild=discord.Object(id=GUILD_ID)
)
@app_commands.describe(
    mensagem="Mensagem que será enviada.",
    anexo="Arquivo ou imagem opcional."
)
async def msg(
    interaction: discord.Interaction,
    mensagem: str,
    anexo: discord.Attachment | None = None
):

    if not tem_cargo(
        interaction.user,
        CARGO_ADMIN
    ):
        await interaction.response.send_message(
            "Você não possui permissão para usar este comando.",
            ephemeral=True
        )
        return

    try:

        if anexo:

            await interaction.channel.send(
                content=mensagem,
                file=await anexo.to_file()
            )

        else:

            await interaction.channel.send(
                content=mensagem
            )

        await interaction.response.send_message(
            "Mensagem enviada.",
            ephemeral=True
        )

    except Exception as erro:

        print(
            f"Erro no /msg: {erro}"
        )

        await interaction.response.send_message(
            "Não consegui enviar a mensagem.",
            ephemeral=True
        )


# ============================================================
# PAINEL PONTO
# ============================================================

@bot.tree.command(
    name="painel_ponto",
    description="Envia o painel de ponto.",
    guild=discord.Object(id=GUILD_ID)
)
async def painel_ponto(
    interaction: discord.Interaction
):

    if not tem_cargo(
        interaction.user,
        CARGO_ADMIN
    ):
        await interaction.response.send_message(
            "Você não possui permissão.",
            ephemeral=True
        )
        return

    canal = bot.get_channel(
        CANAL_PONTO
    )

    if canal is None:
        await interaction.response.send_message(
            "Canal de ponto não encontrado.",
            ephemeral=True
        )
        return

    embed = discord.Embed(
        title="CONTROLE DE SERVIÇO",
        description=(
            "**INICIAR SERVIÇO**\n"
            "O P2 informa o modelo e o prefixo da VTR.\n\n"
            "**TEMPO INDIVIDUAL**\n"
            "Cada policial terá seu próprio tempo "
            "registrado ao entrar e sair da QSV.\n\n"
            "**ENCERRAR SERVIÇO**\n"
            "O serviço é encerrado e a QSV é apagada."
        ),
        color=discord.Color.red()
    )

    embed.set_footer(
        text="PRF - BOT | Controle de Serviço"
    )

    await canal.send(
        embed=embed,
        view=PontoView()
    )

    await interaction.response.send_message(
        f"Painel enviado em {canal.mention}.",
        ephemeral=True
    )


# ============================================================
# PAINEL RH
# ============================================================

@bot.tree.command(
    name="painel_rh",
    description="Envia o painel do RH.",
    guild=discord.Object(id=GUILD_ID)
)
async def painel_rh(
    interaction: discord.Interaction
):

    if not tem_cargo(
        interaction.user,
        CARGO_ADMIN
    ):
        await interaction.response.send_message(
            "Você não possui permissão.",
            ephemeral=True
        )
        return

    canal = bot.get_channel(
        CANAL_RH
    )

    if canal is None:
        await interaction.response.send_message(
            "Canal do RH não encontrado.",
            ephemeral=True
        )
        return

    embed = discord.Embed(
        title="RECURSOS HUMANOS",
        description=(
            "Precisa falar com o RH?\n\n"
            "Clique abaixo para abrir um atendimento privado."
        ),
        color=discord.Color.red()
    )

    embed.set_footer(
        text="PRF - BOT | Recursos Humanos"
    )

    await canal.send(
        embed=embed,
        view=RHView()
    )

    await interaction.response.send_message(
        f"Painel enviado em {canal.mention}.",
        ephemeral=True
    )


# ============================================================
# PAINEL SET
# ============================================================

@bot.tree.command(
    name="painel_set",
    description="Envia o painel de SET.",
    guild=discord.Object(id=GUILD_ID)
)
async def painel_set(
    interaction: discord.Interaction
):

    if not tem_cargo(
        interaction.user,
        CARGO_ADMIN
    ):
        await interaction.response.send_message(
            "Você não possui permissão.",
            ephemeral=True
        )
        return

    canal = bot.get_channel(
        CANAL_SET
    )

    if canal is None:
        await interaction.response.send_message(
            "Canal de SET não encontrado.",
            ephemeral=True
        )
        return

    embed = discord.Embed(
        title="SOLICITAÇÃO DE SET",
        description=(
            "Clique abaixo para solicitar um SET.\n\n"
            "**Informações:**\n"
            "• Nome\n"
            "• ID DA CIDADE\n"
            "• Cargo desejado\n"
            "• Motivo"
        ),
        color=discord.Color.red()
    )

    await canal.send(
        embed=embed,
        view=SETView()
    )

    await interaction.response.send_message(
        f"Painel enviado em {canal.mention}.",
        ephemeral=True
    )


# ============================================================
# PAINEL AUSÊNCIA
# ============================================================

@bot.tree.command(
    name="painel_ausencia",
    description="Envia o painel de ausência.",
    guild=discord.Object(id=GUILD_ID)
)
async def painel_ausencia(
    interaction: discord.Interaction
):

    if not tem_cargo(
        interaction.user,
        CARGO_ADMIN
    ):
        await interaction.response.send_message(
            "Você não possui permissão.",
            ephemeral=True
        )
        return

    canal = bot.get_channel(
        CANAL_AUSENCIA
    )

    if canal is None:
        await interaction.response.send_message(
            "Canal de ausência não encontrado.",
            ephemeral=True
        )
        return

    embed = discord.Embed(
        title="REGISTRO DE AUSÊNCIA",
        description=(
            "Clique abaixo para registrar sua ausência.\n\n"
            "O cargo de ausência será atribuído automaticamente."
        ),
        color=discord.Color.orange()
    )

    await canal.send(
        embed=embed,
        view=AusenciaView()
    )

    await interaction.response.send_message(
        f"Painel enviado em {canal.mention}.",
        ephemeral=True
    )


# ============================================================
# PAINEL APREENSÕES
# ============================================================

@bot.tree.command(
    name="painel_apreendidos",
    description="Envia o painel de apreensões.",
    guild=discord.Object(id=GUILD_ID)
)
async def painel_apreendidos(
    interaction: discord.Interaction
):

    if not tem_cargo(
        interaction.user,
        CARGO_ADMIN
    ):
        await interaction.response.send_message(
            "Você não possui permissão.",
            ephemeral=True
        )
        return

    canal = bot.get_channel(
        CANAL_APREENDIDOS
    )

    if canal is None:
        await interaction.response.send_message(
            "Canal de apreendidos não encontrado.",
            ephemeral=True
        )
        return

    embed = discord.Embed(
        title="REGISTRO DE APREENSÃO",
        description=(
            "Clique abaixo para registrar uma apreensão.\n\n"
            "A descrição da ocorrência deve possuir "
            "no mínimo 4 linhas."
        ),
        color=discord.Color.red()
    )

    await canal.send(
        embed=embed,
        view=ApreensaoView()
    )

    await interaction.response.send_message(
        f"Painel enviado em {canal.mention}.",
        ephemeral=True
    )


# ============================================================
# PAINEL ADVERTÊNCIA
# ============================================================

@bot.tree.command(
    name="painel_advertencia",
    description="Envia o painel de advertências.",
    guild=discord.Object(id=GUILD_ID)
)
async def painel_advertencia(
    interaction: discord.Interaction
):

    if not tem_cargo(
        interaction.user,
        CARGO_SUPERIOR
    ):
        await interaction.response.send_message(
            "Somente superiores podem usar este painel.",
            ephemeral=True
        )
        return

    canal = bot.get_channel(
        CANAL_ADVERTENCIA
    )

    if canal is None:
        await interaction.response.send_message(
            "Canal de advertências não encontrado.",
            ephemeral=True
        )
        return

    embed = discord.Embed(
        title="ADVERTÊNCIAS",
        description=(
            "Somente superiores podem aplicar advertências.\n\n"
            "Clique abaixo para selecionar o policial."
        ),
        color=discord.Color.orange()
    )

    embed.set_footer(
        text="PRF - BOT | Sistema de Advertências"
    )

    await canal.send(
        embed=embed,
        view=AdvertenciaView()
    )

    await interaction.response.send_message(
        f"Painel enviado em {canal.mention}.",
        ephemeral=True
    )


# ============================================================
# MEU PONTO
# ============================================================

@bot.tree.command(
    name="meuponto",
    description="Mostra seu tempo total de serviço.",
    guild=discord.Object(id=GUILD_ID)
)
async def meuponto(
    interaction: discord.Interaction
):

    cursor.execute(
        """
        SELECT COALESCE(SUM(duracao), 0)
        FROM pontos
        WHERE user_id = ?
        """,
        (interaction.user.id,)
    )

    resultado = cursor.fetchone()

    total = (
        resultado[0]
        if resultado
        else 0
    )

    embed = discord.Embed(
        title="MEU PONTO",
        description=(
            f"Policial: {interaction.user.mention}\n\n"
            f"Tempo total: {formatar_tempo(total)}"
        ),
        color=discord.Color.red()
    )

    await interaction.response.send_message(
        embed=embed,
        ephemeral=True
    )


# ============================================================
# RANKING
# ============================================================

@bot.tree.command(
    name="ranking",
    description="Mostra o ranking de horas.",
    guild=discord.Object(id=GUILD_ID)
)
async def ranking(
    interaction: discord.Interaction
):

    cursor.execute(
        """
        SELECT user_id, nome, SUM(duracao) AS total
        FROM pontos
        GROUP BY user_id
        ORDER BY total DESC
        LIMIT 20
        """
    )

    resultados = cursor.fetchall()

    if not resultados:
        await interaction.response.send_message(
            "Ainda não existem registros.",
            ephemeral=True
        )
        return

    linhas = []

    for posicao, (
        user_id,
        nome,
        total
    ) in enumerate(
        resultados,
        start=1
    ):

        linhas.append(
            f"**{posicao}.** <@{user_id}> "
            f"• {formatar_tempo(total)}"
        )

    embed = discord.Embed(
        title="RANKING DE SERVIÇO",
        description="\n".join(linhas),
        color=discord.Color.red()
    )

    embed.set_footer(
        text="PRF - BOT"
    )

    await interaction.response.send_message(
        embed=embed
    )


# ============================================================
# VOICE STATE
# ============================================================

@bot.event
async def on_voice_state_update(
    member,
    before,
    after
):

    # Entrou em uma QSV
    if (
        after.channel
        and after.channel.id in servicos
    ):

        entrar_servico(
            after.channel.id,
            member
        )

    # Saiu de uma QSV
    if (
        before.channel
        and before.channel.id in servicos
        and (
            after.channel is None
            or after.channel.id
            != before.channel.id
        )
    ):

        sair_servico(
            before.channel.id,
            member
        )


# ============================================================
# SETUP
# ============================================================

@bot.event
async def setup_hook():

    bot.add_view(
        PontoView()
    )

    bot.add_view(
        RHView()
    )

    bot.add_view(
        SETView()
    )

    bot.add_view(
        AusenciaView()
    )

    bot.add_view(
        ApreensaoView()
    )

    bot.add_view(
        AdvertenciaView()
    )

    guild = discord.Object(
        id=GUILD_ID
    )

    bot.tree.copy_global_to(
        guild=guild
    )

    await bot.tree.sync(
        guild=guild
    )

    print(
        "Comandos sincronizados!"
    )


# ============================================================
# ERROS
# ============================================================

@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction,
    error
):

    print(
        f"Erro no comando "
        f"{getattr(interaction.command, 'name', 'desconhecido')}: "
        f"{error}"
    )

    try:

        if interaction.response.is_done():

            await interaction.followup.send(
                "Ocorreu um erro ao executar o comando.",
                ephemeral=True
            )

        else:

            await interaction.response.send_message(
                "Ocorreu um erro ao executar o comando.",
                ephemeral=True
            )

    except Exception as erro:

        print(
            f"Erro ao enviar erro: {erro}"
        )


# ============================================================
# READY
# ============================================================

@bot.event
async def on_ready():

    print("=" * 60)
    print("PRF - BOT")
    print(f"Bot: {bot.user}")
    print(f"ID: {bot.user.id}")
    print(f"Servidor: {GUILD_ID}")
    print("BOT ONLINE!")
    print("=" * 60)


# ============================================================
# INICIAR
# ============================================================

if not TOKEN:

    print(
        "ERRO: DISCORD_TOKEN não foi encontrado no .env"
    )

else:

    bot.run(TOKEN)
