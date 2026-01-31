import discord
from discord.ext import commands, tasks
from discord.ui import View, Button, Modal, TextInput, RoleSelect, ChannelSelect
import sqlite3
import aiohttp
import os
import datetime
import asyncio
import logging
import sys

# ==============================================================================
#                         DIRETRIZES DE CONFIGURAÇÃO E AMBIENTE
# ==============================================================================
# Configuração de alto nível para garantir a estabilidade do bot na Railway.
# Mantenha o TOKEN seguro nas variáveis de ambiente.

TOKEN = os.getenv("TOKEN")

# Identidade Visual Padronizada (WS APOSTAS)
BANNER_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"
ICONE_ORG = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"
COR_PADRAO = 0x2b2d31  # Cinza Escuro Profissional Discord

# Parâmetros Financeiros
COMISSAO_FIXA = 0.10  # Valor fixo de comissão por partida (R$ 0,10)

# Inicialização de Intents (Permissões de Gateway)
intents = discord.Intents.all()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix=".", intents=intents, help_command=None)

# ==============================================================================
#                         MÓDULO DE LOGS E AUDITORIA (SYSTEM LOGGER)
# ==============================================================================
class SistemaAuditoria:
    """
    Classe responsável por registrar todos os eventos do sistema no console
    e manter um rastro de auditoria para depuração na Railway.
    """
    @staticmethod
    def log(nivel, modulo, mensagem):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        formatado = f"[{timestamp}] [{nivel.upper()}] [{modulo}] : {mensagem}"
        print(formatado)

    @staticmethod
    def info(modulo, mensagem):
        SistemaAuditoria.log("INFO", modulo, mensagem)

    @staticmethod
    def erro(modulo, mensagem):
        SistemaAuditoria.log("ERRO", modulo, mensagem)

    @staticmethod
    def alerta(modulo, mensagem):
        SistemaAuditoria.log("ALERTA", modulo, mensagem)

# ==============================================================================
#                         GERENCIADOR DE BANCO DE DADOS (DB MANAGER)
# ==============================================================================
class GerenciadorBancoDados:
    """
    Controlador robusto para conexões SQLite, garantindo que as transações
    sejam atômicas e seguras contra falhas de concorrência.
    """
    def __init__(self, db_name="ws_sistema_integral.db"):
        self.db_name = db_name
        self.inicializar_tabelas()

    def conectar(self):
        return sqlite3.connect(self.db_name)

    def inicializar_tabelas(self):
        SistemaAuditoria.info("DB", "Verificando integridade das tabelas...")
        with self.conectar() as conn:
            cursor = conn.cursor()
            
            # Tabela de PIX e Saldo
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pix (
                    user_id INTEGER PRIMARY KEY,
                    nome_titular TEXT,
                    chave_pix TEXT,
                    url_qrcode TEXT,
                    saldo_acumulado REAL DEFAULT 0.0,
                    partidas_mediadas INTEGER DEFAULT 0,
                    data_cadastro TEXT
                )
            """)
            
            # Tabela de Configurações (Chave-Valor)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS configuracoes (
                    chave TEXT PRIMARY KEY,
                    valor TEXT
                )
            """)
            
            # Tabela de Restrições (Banimentos internos)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS restricoes (
                    user_id INTEGER PRIMARY KEY,
                    motivo TEXT,
                    admin_responsavel INTEGER,
                    data_restricao TEXT
                )
            """)
            
            # Tabela de Histórico de Partidas
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS historico_partidas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mediador_id INTEGER,
                    valor_entrada TEXT,
                    modo_jogo TEXT,
                    participantes TEXT,
                    data_hora TEXT
                )
            """)
            conn.commit()
        SistemaAuditoria.info("DB", "Tabelas verificadas e operacionais.")

    def executar(self, query, parametros=()):
        """Executa uma instrução SQL de escrita (INSERT, UPDATE, DELETE)."""
        try:
            with self.conectar() as conn:
                cursor = conn.cursor()
                cursor.execute(query, parametros)
                conn.commit()
        except sqlite3.Error as e:
            SistemaAuditoria.erro("DB_EXEC", f"Falha na query: {e}")

    def consultar(self, query, parametros=()):
        """Executa uma consulta SQL de leitura (SELECT) retornando um único registro."""
        try:
            with self.conectar() as conn:
                cursor = conn.cursor()
                cursor.execute(query, parametros)
                return cursor.fetchone()
        except sqlite3.Error as e:
            SistemaAuditoria.erro("DB_QUERY", f"Falha na consulta: {e}")
            return None

    def consultar_todos(self, query, parametros=()):
        """Executa uma consulta SQL de leitura retornando todos os registros."""
        try:
            with self.conectar() as conn:
                cursor = conn.cursor()
                cursor.execute(query, parametros)
                return cursor.fetchall()
        except sqlite3.Error as e:
            SistemaAuditoria.erro("DB_ALL", f"Falha na consulta múltipla: {e}")
            return []

# Instância Global do Banco de Dados
db = GerenciadorBancoDados()

# ==============================================================================
#                         VARIÁVEIS GLOBAIS DE ESTADO
# ==============================================================================
# Fila volátil de mediadores (Reseta ao reiniciar, mas é gerida pelo comando .mediar)
FILA_MEDIADORES = []

# ==============================================================================
#                         INTERFACE: GESTÃO DE FILAS (VIEW LOGIC)
# ==============================================================================
class ViewFilaApostas(View):
    """
    Interface Gráfica Complexa para gestão de entrada e saída de jogadores.
    Gerencia estados 1v1 (Gelo) e Coletivos (/entrar).
    """
    def __init__(self, modo: str, valor: str):
        super().__init__(timeout=None) # Timeout None para persistência
        self.modo = modo
        self.valor = valor
        self.jogadores = [] # Lista de dicionários {'id': int, 'mention': str}
        self.lock = asyncio.Lock() # Previne Race Conditions
        
        # Inicializa a construção dos botões
        self._construir_interface()

    def _construir_interface(self):
        """Define dinamicamente os botões baseados no modo de jogo."""
        self.clear_items()
        
        modo_upper = self.modo.upper()
        
        # ======================================================================
        # LÓGICA ESPECÍFICA PARA 1V1 (GELO)
        # ======================================================================
        if "1V1" in modo_upper:
            # Botão Gelo Normal (Cinza/Secondary)
            btn_normal = Button(
                label="Gelo Normal",
                style=discord.ButtonStyle.secondary,
                custom_id=f"ws_btn_normal_{self.valor}"
            )
            btn_normal.callback = self.callback_gelo_normal
            self.add_item(btn_normal)
            
            # Botão Gelo Infinito (Cinza/Secondary)
            btn_infinito = Button(
                label="Gelo Infinito",
                style=discord.ButtonStyle.secondary,
                custom_id=f"ws_btn_infinito_{self.valor}"
            )
            btn_infinito.callback = self.callback_gelo_infinito
            self.add_item(btn_infinito)
            
            # Botão Sair (Vermelho/Danger)
            btn_sair = Button(
                label="Sair da Fila",
                style=discord.ButtonStyle.danger,
                custom_id=f"ws_btn_sair_{self.valor}",
                emoji="✖️"
            )
            btn_sair.callback = self.callback_sair
            self.add_item(btn_sair)

        # ======================================================================
        # LÓGICA PARA MODOS COLETIVOS (2v2, 4v4, SQUAD)
        # ======================================================================
        else:
            # Botão Entrar Padrão (Verde/Success)
            btn_entrar = Button(
                label="/entrar na fila",
                style=discord.ButtonStyle.success,
                custom_id=f"ws_btn_entrar_{self.valor}",
                emoji="✅"
            )
            btn_entrar.callback = self.callback_entrar_padrao
            self.add_item(btn_entrar)
            
            # Botão Sair (Vermelho/Danger)
            btn_sair = Button(
                label="Sair da Fila",
                style=discord.ButtonStyle.danger,
                custom_id=f"ws_btn_sair_coletivo_{self.valor}",
                emoji="✖️"
            )
            btn_sair.callback = self.callback_sair
            self.add_item(btn_sair)

    # --------------------------------------------------------------------------
    # CALLBACKS DOS BOTÕES (AÇÕES)
    # --------------------------------------------------------------------------
    
    async def callback_gelo_normal(self, interaction: discord.Interaction):
        """Processa o clique em Gelo Normal."""
        await self._processar_entrada(interaction, tipo_gelo="gelo normal")

    async def callback_gelo_infinito(self, interaction: discord.Interaction):
        """Processa o clique em Gelo Infinito."""
        await self._processar_entrada(interaction, tipo_gelo="gelo infinito")

    async def callback_entrar_padrao(self, interaction: discord.Interaction):
        """Processa a entrada em modos coletivos."""
        await self._processar_entrada(interaction, tipo_gelo=None)

    async def callback_sair(self, interaction: discord.Interaction):
        """Remove o usuário da fila."""
        async with self.lock:
            # Filtra a lista removendo o ID do usuário
            nova_lista = [j for j in self.jogadores if j['id'] != interaction.user.id]
            
            if len(nova_lista) == len(self.jogadores):
                await interaction.response.send_message("Você não está nesta fila.", ephemeral=True)
                return
            
            self.jogadores = nova_lista
            await interaction.response.edit_message(embed=self._gerar_embed_visual())

    # --------------------------------------------------------------------------
    # NÚCLEO LÓGICO DE ENTRADA
    # --------------------------------------------------------------------------
    async def _processar_entrada(self, interaction: discord.Interaction, tipo_gelo=None):
        """Lógica central de validação e registro de usuários na fila."""
        
        # 1. Verificação de Restrições (Banimentos)
        restricao = db.consultar("SELECT motivo FROM restricoes WHERE user_id = ?", (interaction.user.id,))
        if restricao:
            await interaction.response.send_message(
                f"🚫 **ACESSO NEGADO**: Você possui uma restrição ativa.\nMotivo: {restricao[0]}", 
                ephemeral=True
            )
            return

        async with self.lock:
            # 2. Verificação de Duplicidade
            if any(jogador['id'] == interaction.user.id for jogador in self.jogadores):
                await interaction.response.send_message("Você já está inscrito nesta fila.", ephemeral=True)
                return

            # 3. Notificação de Gelo (Se aplicável)
            if tipo_gelo:
                # Envia a mensagem no chat: @Usuario-gelo infinito
                await interaction.channel.send(f"{interaction.user.mention}-{tipo_gelo}")

            # 4. Registro na Memória
            self.jogadores.append({'id': interaction.user.id, 'mention': interaction.user.mention})
            
            # 5. Atualização Visual
            await interaction.response.edit_message(embed=self._gerar_embed_visual())
            
            # 6. Verificação de Fechamento da Sala
            await self._verificar_fechamento(interaction)

    def _gerar_embed_visual(self):
        """Constrói o Embed rico visualmente."""
        embed = discord.Embed(title=f"SESSÃO DE APOSTAS | {self.modo.upper()}", color=COR_PADRAO)
        embed.set_author(name="WS APOSTAS - GESTÃO PROFISSIONAL", icon_url=ICONE_ORG)
        
        # Campo de Valor
        embed.add_field(
            name="💰 Valor da Entrada", 
            value=f"```R$ {self.valor}```", 
            inline=True
        )
        
        # Campo de Modalidade
        embed.add_field(
            name="🎮 Modalidade", 
            value=f"```{self.modo}```", 
            inline=True
        )
        
        # Lista de Participantes
        if len(self.jogadores) == 0:
            lista_texto = "*Aguardando proponentes...*"
        else:
            lista_texto = "\n".join([f"👤 {j['mention']}" for j in self.jogadores])
            
        embed.add_field(name="👥 Participantes Inscritos", value=lista_texto, inline=False)
        
        embed.set_image(url=BANNER_URL)
        embed.set_footer(text=f"WS Apostas 2026 | Sistema Seguro v5.5 | ID: {interaction_id_mock()}")
        
        return embed

    async def _verificar_fechamento(self, interaction: discord.Interaction):
        """Verifica se a fila atingiu o limite e processa o início da partida."""
        
        # Determina o limite baseado no nome do modo (ex: 1v1 = 2, 2v2 = 4)
        try:
            primeiro_digito = int(self.modo[0])
            limite_maximo = primeiro_digito * 2
        except (ValueError, IndexError):
            limite_maximo = 2 # Fallback seguro

        if len(self.jogadores) >= limite_maximo:
            # Verifica disponibilidade de mediadores
            if not FILA_MEDIADORES:
                await interaction.channel.send("⚠️ **ALERTA**: Nenhum mediador disponível na escala no momento. Aguardem.", delete_after=10)
                return

            # Seleção de Mediador (Round Robin / Rotativo)
            mediador_id = FILA_MEDIADORES.pop(0)
            FILA_MEDIADORES.append(mediador_id) # Coloca no final da fila

            # Processamento Financeiro (Comissão)
            self._registrar_comissao(mediador_id)
            
            # Criação do Tópico (Thread)
            await self._criar_topico_partida(interaction, mediador_id)
            
            # Limpeza da Fila
            self.jogadores = []
            
            # Atualização final do Embed (para mostrar vazio)
            msg = await interaction.original_response()
            await msg.edit(embed=self._gerar_embed_visual())

    def _registrar_comissao(self, mediador_id):
        """Atualiza o saldo do mediador no banco de dados."""
        SistemaAuditoria.info("FINANCEIRO", f"Creditando comissão para {mediador_id}")
        db.executar("""
            UPDATE pix 
            SET saldo_acumulado = saldo_acumulado + ?, 
                partidas_mediadas = partidas_mediadas + 1 
            WHERE user_id = ?
        """, (COMISSAO_FIXA, mediador_id))
        
        # Log de segurança
        participantes_str = ",".join([str(j['id']) for j in self.jogadores])
        db.executar("""
            INSERT INTO historico_partidas (mediador_id, valor_entrada, modo_jogo, participantes, data_hora)
            VALUES (?, ?, ?, ?, ?)
        """, (mediador_id, self.valor, self.modo, participantes_str, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

    async def _criar_topico_partida(self, interaction: discord.Interaction, mediador_id: int):
        """Cria o canal de texto temporário (Thread) para a partida."""
        config_canal = db.consultar("SELECT valor FROM configuracoes WHERE chave = 'canal_th'")
        
        if not config_canal:
            SistemaAuditoria.erro("CONFIG", "Canal de threads (canal_th) não configurado!")
            await interaction.channel.send("❌ Erro de Configuração: Canal de destino não definido.")
            return

        canal_destino_id = int(config_canal[0])
        canal_destino = interaction.guild.get_channel(canal_destino_id)
        
        if canal_destino:
            nome_topico = f"Sessão-{self.valor}-ID{str(interaction.id)[-4:]}"
            topico = await canal_destino.create_thread(
                name=nome_topico,
                type=discord.ChannelType.public_thread
            )
            
            # Mensagem de Início no Tópico
            participantes_mentions = " ".join([j['mention'] for j in self.jogadores])
            await topico.send(
                content=f"🔔 **NOVA SESSÃO INICIADA**\n\n"
                        f"👮‍♂️ **Mediador Responsável:** <@{mediador_id}>\n"
                        f"💰 **Valor:** R$ {self.valor}\n"
                        f"👥 **Jogadores:** {participantes_mentions}\n\n"
                        f"aguardando sala..."
            )
        else:
            await interaction.channel.send("❌ Erro: Canal de tópicos não encontrado.")

def interaction_id_mock():
    """Gera um ID visual aleatório para o footer."""
    import random
    return random.randint(100000, 999999)

# ==============================================================================
#                         PAINEL ADMINISTRATIVO: MEDIADORES
# ==============================================================================
class ViewControleMediadores(View):
    """
    Painel persistente para mediadores entrarem e saírem do plantão (Escala).
    Restaura o visual original solicitado.
    """
    def __init__(self):
        super().__init__(timeout=None)

    def gerar_embed_escala(self):
        """Gera a lista visual de quem está trabalhando."""
        embed = discord.Embed(title="📋 Controle de Escala Operacional", color=0x36393f)
        embed.description = "Utilize os botões abaixo para gerenciar seu status de plantão.\n\n**Mediadores Ativos:**\n"
        
        if not FILA_MEDIADORES:
            embed.description += "*Nenhum mediador em plantão no momento.*"
        else:
            for index, uid in enumerate(FILA_MEDIADORES):
                embed.description += f"**{index + 1}.** <@{uid}>\n"
        
        embed.set_footer(text="WS Apostas | Gestão de Equipe")
        return embed

    @discord.ui.button(label="Iniciar Plantão", style=discord.ButtonStyle.success, custom_id="ws_med_entrar")
    async def btn_entrar(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in FILA_MEDIADORES:
            FILA_MEDIADORES.append(interaction.user.id)
            SistemaAuditoria.log("ESCALA", "ENTRADA", f"{interaction.user.name} iniciou plantão.")
            await interaction.response.edit_message(embed=self.gerar_embed_escala())
        else:
            await interaction.response.send_message("Você já está na escala.", ephemeral=True)

    @discord.ui.button(label="Encerrar Plantão", style=discord.ButtonStyle.danger, custom_id="ws_med_sair")
    async def btn_sair(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id in FILA_MEDIADORES:
            FILA_MEDIADORES.remove(interaction.user.id)
            SistemaAuditoria.log("ESCALA", "SAIDA", f"{interaction.user.name} encerrou plantão.")
            await interaction.response.edit_message(embed=self.gerar_embed_esca
