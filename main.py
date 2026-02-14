import discord
import os
import asyncio
import datetime
import traceback
import random
from discord.ext import commands
from discord import app_commands

TOKEN = os.getenv("DISCORD_TOKEN")
DONO_ID = 1461858587080130663

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- MEMÓRIA ---
configuracao = {
    "cargos": {"ver": [], "finalizar": []},
    "canais": {"Filas": []}, 
    "contador_salas": 0,
    "cargo_mediador_id": None,
    "dados_mediadores": {} 
}
tickets_abertos = []
mediadores_ativos = []

# ==============================================================================
# 1. MENU MEDIADOR (Dropdown da Imagem 6)
# ==============================================================================

class MenuMediadorSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Escolha o vencedor", description="Defina o vencedor da aposta.", emoji="👑", value="vencedor"),
            discord.SelectOption(label="Finalizar aposta", description="Clique aqui para finalizar a aposta!", emoji="🟥", value="finalizar"),
            discord.SelectOption(label="Vitória por W.O", description="Clique aqui para dar vitória por W.O!", emoji="🛠️", value="wo"),
            discord.SelectOption(label="Liberar Pix", description="Clique aqui para liberar o envio do pix!", emoji="💠", value="liberar_pix")
        ]
        super().__init__(placeholder="Menu Mediador", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        # Verifica permissão
        perm = False
        if interaction.user.id == DONO_ID or interaction.user.guild_permissions.manage_messages: perm = True
        if configuracao["cargo_mediador_id"]:
            role = interaction.guild.get_role(configuracao["cargo_mediador_id"])
            if role in interaction.user.roles: perm = True
        
        if not perm:
            return await interaction.response.send_message("❌ Apenas o Mediador/Staff.", ephemeral=True)

        escolha = self.values[0]
        if escolha == "vencedor":
            await interaction.response.send_message("🏆 **Vencedor Selecionado!** (Implementar lógica de vitória)", ephemeral=True)
        elif escolha == "finalizar":
            await interaction.response.send_message("🟥 **Aposta Finalizada!** Fechando em 5s...", ephemeral=False)
            await asyncio.sleep(5)
            await interaction.channel.delete()
        elif escolha == "wo":
            await interaction.response.send_message("🛠️ **Vitória por W.O Aplicada!**", ephemeral=False)
        elif escolha == "liberar_pix":
            await interaction.response.send_message("💠 **Pix Liberado!** (O QR Code já foi enviado acima)", ephemeral=True)

class MenuMediadorView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(MenuMediadorSelect())

# ==============================================================================
# 2. FASE 2: PARTIDA CONFIRMADA (Imagem 3 e 5)
# ==============================================================================

class PartidaConfirmadaView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        # Botão Menu Mediador (Abre o Dropdown)
        self.add_item(discord.ui.Button(label="Menu Mediador", style=discord.ButtonStyle.secondary, custom_id="btn_menu_med", row=0))
        # Botão Regras (Link ou Texto)
        self.add_item(discord.ui.Button(label="Regras", style=discord.ButtonStyle.secondary, emoji="↗️", url="https://discord.gg/exemplo", row=0))

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.data["custom_id"] == "btn_menu_med":
            # Envia o menu dropdown de forma efêmera ou no chat
            await interaction.response.send_message("Selecione uma ação:", view=MenuMediadorView(), ephemeral=True)
        return False

# ==============================================================================
# 3. FASE 1: AGUARDANDO CONFIRMAÇÃO (Imagem 2, 4 e 7)
# ==============================================================================

class AguardandoConfirmacaoView(discord.ui.View):
    def __init__(self, jogadores, modo, valor):
        super().__init__(timeout=None)
        self.jogadores = jogadores
        self.modo = modo
        self.valor = valor
        self.confirmados = []

    async def atualizar_fase_final(self, interaction):
        if len(self.confirmados) >= len(self.jogadores):
            # --- TRANSIÇÃO PARA FASE 2 ---
            
            # 1. Rotação do Mediador
            dados_pix = None
            mediador_txt = "Sem Mediador Online"
            if mediadores_ativos:
                mediador_id = mediadores_ativos.pop(0)
                mediadores_ativos.append(mediador_id)
                dados = configuracao["dados_mediadores"].get(mediador_id)
                if dados:
                    dados_pix = dados
                    mediador_txt = f"<@{mediador_id}>"
            
            if not dados_pix: # Fallback
                dados_pix = {"nome": "Admin", "chave": "Chave Admin", "qrcode": "https://cdn.discordapp.com/attachments/1465403221936963655/1465775330999533773/file_00000000d78871f596a846e9ca08d27c.jpg"}

            # 2. Renomear Tópico e Limpar Chat
            configuracao["contador_salas"] += 1
            num = configuracao["contador_salas"]
            tipo = "emulador" if "emulador" in self.modo.lower() else "mobile"
            await interaction.channel.edit(name=f"{tipo}-{num}")
            await interaction.channel.purge(limit=100) # Limpa a fase de confirmação

            # 3. Painel Final (Igual Imagem 3)
            embed_final = discord.Embed(title="Partida Confirmada", color=discord.Color.from_rgb(88, 101, 242)) # Blurple
            embed_final.set_thumbnail(url="https://cdn.discordapp.com/attachments/1465403221936963655/1465775330999533773/file_00000000d78871f596a846e9ca08d27c.jpg") # Boneca
            
            embed_final.add_field(name="🎮 Estilo de Jogo", value=f"{self.modo}", inline=False)
            embed_final.add_field(name="ℹ️ Informações da Aposta", value=f"Valor Da Sala: {self.valor}\nMediador: {mediador_txt}", inline=False)
            embed_final.add_field(name="💸 Valor da Aposta", value=f"{self.valor}", inline=False)
            
            jogadores_fmt = "\n".join([f"<@{u}>" for u in self.jogadores])
            embed_final.add_field(name="👥 Jogadores", value=jogadores_fmt, inline=False)
            
            await interaction.channel.send(embed=embed_final)

            # 4. QR Code Grande e Dados (Imagem 5)
            embed_qr = discord.Embed(color=discord.Color.dark_theme())
            embed_qr.set_image(url=dados_pix["qrcode"])
            await interaction.channel.send(embed=embed_qr)

            msg_pix = (
                f"**{dados_pix['nome']}**\n"
                f"{dados_pix['chave']}\n"
                f"↪ Valor a pagar: {self.valor}"
            )
            await interaction.channel.send(content=msg_pix, view=PartidaConfirmadaView())

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.success, custom_id="btn_conf")
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in self.jogadores:
            return await interaction.response.send_message("❌ Você não está na partida.", ephemeral=True)
        
        if interaction.user.id in self.confirmados:
            return await interaction.response.send_message("✅ Você já confirmou.", ephemeral=True)

        self.confirmados.append(interaction.user.id)
        
        # Mensagem de Confirmação Individual (Igual Imagem 7)
        embed_aviso = discord.Embed(title="✅ | Partida Confirmada", description=f"{interaction.user.mention} confirmou a aposta!\n↪ O outro jogador precisa confirmar para continuar.", color=discord.Color.green())
        await interaction.channel.send(embed=embed_aviso)
        
        await interaction.response.defer() # Apenas para não falhar a interação
        await self.atualizar_fase_final(interaction)

    @discord.ui.button(label="Recusar", style=discord.ButtonStyle.danger, custom_id="btn_recus")
    async def recusar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in self.jogadores: return
        await interaction.channel.send(f"❌ **{interaction.user.display_name}** recusou. Cancelando...")
        await asyncio.sleep(3)
        await interaction.channel.delete()

    @discord.ui.button(label="Combinar Regras", style=discord.ButtonStyle.secondary, emoji="🏳️", custom_id="btn_regras")
    async def regras(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(f"📢 {interaction.user.mention} quer combinar regras!", ephemeral=False)

# ==============================================================================
# 4. LOBBY E CRIAÇÃO DO TICKET (AGUARDANDO-CONFIRMACAO)
# ==============================================================================

class FilaLobbyView(discord.ui.View):
    def __init__(self, modo: str, valor: str, limite: int):
        super().__init__(timeout=None)
        self.limite, self.modo, self.valor = limite, modo, valor
        self.jogadores, self.dados_visuais = [], {}
        self.configurar_botoes()

    def configurar_botoes(self):
        self.clear_items()
        self.add_item(discord.ui.Button(label="Gel Normal", style=discord.ButtonStyle.secondary, custom_id="j_norm"))
        self.add_item(discord.ui.Button(label="Gel Infinito", style=discord.ButtonStyle.secondary, custom_id="j_inf"))
        self.add_item(discord.ui.Button(label="Sair da Fila", style=discord.ButtonStyle.danger, custom_id="l_fila"))

    async def atualizar_embed(self, interaction):
        texto = "Nenhum jogador na fila" if not self.jogadores else "".join([f"<@{u}> | {self.dados_visuais.get(u,'Entrou')}\n" for u in self.jogadores])
        embed = interaction.message.embeds[0]
        embed.set_field_at(2, name="👥 | Jogadores", value=texto, inline=False)
        await interaction.message.edit(embed=embed, view=self)

    async def iniciar_sala(self, interaction):
        canais = configuracao["canais"].get("Filas", [])
        canal_destino = random.choice(canais) if canais else interaction.channel
        
        # Cria Tópico com nome AGUARDANDO-CONFIRMACAO (Imagem 2)
        thread = await canal_destino.create_thread(name="aguardando-confirmacao", type=discord.ChannelType.private_thread)
        
        mencoes = ""
        objs_jogadores = []
        for u in self.jogadores:
            obj = interaction.guild.get_member(u)
            if obj: 
                await thread.add_user(obj)
                mencoes += f"{obj.mention} "
                objs_jogadores.append(obj)
        
        # 1. Embed de Boas Vindas (Imagem 2 - Parte inferior)
        embed_welcome = discord.Embed(title="✨ SEJAM MUITO BEM-VINDOS ✨", description="• Regras adicionais podem ser combinadas entre os participantes.\n• Se a regra combinada não existir no regulamento oficial da organização, é obrigatório tirar print do acordo antes do início da partida.", color=discord.Color.gold())
        await thread.send(content=mencoes, embed=embed_welcome)

        # 2. Embed Principal Aguardando Confirmação (Imagem 2 - Parte superior)
        embed_conf = discord.Embed(title="Aguardando Confirmações", color=discord.Color.dark_grey())
        embed_conf.set_thumbnail(url="https://cdn.discordapp.com/attachments/1465403221936963655/1465775330999533773/file_00000000d78871f596a846e9ca08d27c.jpg")
        embed_conf.add_field(name="👑 Modo:", value=f"{self.modo}", inline=False)
        embed_conf.add_field(name="💸 Valor da aposta:", value=f"{self.valor}", inline=False)
        
        jogadores_lista = "\n".join([f"{u.mention}" for u in objs_jogadores])
        embed_conf.add_field(name="⚡ Jogadores:", value=jogadores_lista, inline=False)

        await thread.send(embed=embed_conf, view=AguardandoConfirmacaoView(self.jogadores, self.modo, self.valor))
        
        # Limpa fila
        self.jogadores, self.dados_visuais = [], {}
        await self.atualizar_embed(interaction)

    async def interaction_check(self, i):
        cid, uid = i.data["custom_id"], i.user.id
        if cid == "l_fila":
            if uid in self.jogadores:
                self.jogadores.remove(uid); del self.dados_visuais[uid]
                await i.response.defer(); await self.atualizar_embed(i)
            return True
        if uid in self.jogadores or len(self.jogadores) >= self.limite: return False
        
        self.jogadores.append(uid)
        self.dados_visuais[uid] = "Gel Normal" if cid=="j_norm" else "Gel Infinito" if cid=="j_inf" else "Entrou"
        await i.response.defer(); await self.atualizar_embed(i)
        
        if len(self.jogadores) >= self.limite: await self.iniciar_sala(i)
        return True

# ==============================================================================
# 5. CONFIGURAÇÃO DE PIX (PAINEL ROXO - Imagem 2)
# ==============================================================================

class CadastroPixModal(discord.ui.Modal, title="Cadastrar Pix"):
    nome = discord.ui.TextInput(label="Nome Titular")
    chave = discord.ui.TextInput(label="Chave Pix")
    qr = discord.ui.TextInput(label="Link QR Code", style=discord.TextStyle.paragraph)
    async def on_submit(self, i):
        configuracao["dados_mediadores"][i.user.id] = {"nome": self.nome.value, "chave": self.chave.value, "qrcode": self.qr.value}
        await i.response.send_message("✅ PIX Salvo!", ephemeral=True)

class PainelConfigPixView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Chave Pix", style=discord.ButtonStyle.success, emoji="💠", custom_id="pix_k")
    async def k(self, i, b): await i.response.send_modal(CadastroPixModal())
    @discord.ui.button(label="Sua Chave", style=discord.ButtonStyle.success, emoji="🔍", custom_id="pix_v")
    async def v(self, i, b):
        d = configuracao["dados_mediadores"].get(i.user.id)
        if d: await i.response.send_message(f"Nome: {d['nome']}\nChave: {d['chave']}", ephemeral=True)
        else: await i.response.send_message("❌ Sem chave.", ephemeral=True)
    @discord.ui.button(label="Ver Chave de Mediador", style=discord.ButtonStyle.secondary, emoji="👁️", custom_id="pix_o")
    async def o(self, i, b): await i.response.send_message("⚠️ Em breve.", ephemeral=True)

# ==============================================================================
# 6. MEDIADORES (FILA)
# ==============================================================================

class MediadorQueueView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    async def att(self, i):
        txt = "Vazio" if not mediadores_ativos else "\n".join([f"{idx+1}. <@{u}>" for idx,u in enumerate(mediadores_ativos)])
        await i.message.edit(embed=i.message.embeds[0].set_field_at(0, name="Fila", value=txt))

    @discord.ui.button(label="Entrar na fila", style=discord.ButtonStyle.success, emoji="🟢")
    async def entra(self, i, b):
        if i.user.id not in configuracao["dados_mediadores"]: return await i.response.send_message("❌ Cadastre PIX primeiro!", ephemeral=True)
        if i.user.id not in mediadores_ativos: mediadores_ativos.append(i.user.id); await i.response.send_message("✅", ephemeral=True)

    @discord.ui.button(label="Sair da fila", style=discord.ButtonStyle.danger, emoji="🔴")
    async def sai(self, i, b):
        if i.user.id in mediadores_ativos: mediadores_ativos.remove(i.user.id); await i.response.send_message("✅", ephemeral=True)

# ==============================================================================
# 7. COMANDOS GERAIS
# ==============================================================================

class CriarFilasEmMassaModal(discord.ui.Modal, title="Criar Filas (Max 15)"):
    nome = discord.ui.TextInput(label="Nome", placeholder="Ex: 2v2 Mobile")
    valores = discord.ui.TextInput(label="Valores (Separe por BARRA /)", placeholder="Ex: 10,00 / 20,00", style=discord.TextStyle.paragraph)

    async def on_submit(self, interaction: discord.Interaction):
        lista = [v.strip() for v in self.valores.value.split("/") if v.strip()][:15]
        await interaction.response.send_message(f"✅ Criando {len(lista)} filas...", ephemeral=True)
        for val in lista:
            v_fmt = f"R$ {val.replace('R$','').strip()}"
            embed = discord.Embed(title=f"{self.nome.value} | WS APOSTAS", color=discord.Color.blue())
            embed.add_field(name="👑 | Modo", value=self.nome.value, inline=False)
            embed.add_field(name="💸 | Valor", value=v_fmt, inline=False)
            embed.add_field(name="👥 | Jogadores", value="Nenhum jogador na fila", inline=False)
            embed.set_image(url="https://cdn.discordapp.com/attachments/1465403221936963655/1465775330999533773/file_00000000d78871f596a846e9ca08d27c.jpg")
            await interaction.channel.send(embed=embed, view=FilaLobbyView(self.nome.value, v_fmt, 2))
            await asyncio.sleep(1)

@bot.tree.command(name="cadastrar_pix", description="Configurar PIX")
async def cadastrar_pix(i: discord.Interaction):
    embed = discord.Embed(title="Painel Para Configurar Chave PIX", description="Gerencie de forma rápida a chave PIX utilizada nas suas filas.", color=discord.Color.dark_purple())
    embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/1465403221936963655/1465775330999533773/file_00000000d78871f596a846e9ca08d27c.jpg")
    await i.channel.send(embed=embed, view=PainelConfigPixView()); await i.response.send_message("✅", ephemeral=True)

@bot.tree.command(name="criar_filas", description="Criar Filas")
async def criar_filas(i: discord.Interaction):
    if i.user.id == DONO_ID: await i.response.send_modal(CriarFilasEmMassaModal())

@bot.tree.command(name="config_cargo_mediador", description="Cargo Mediador")
async def cfg_cargo(i: discord.Interaction, cargo: discord.Role):
    if i.user.id == DONO_ID: configuracao["cargo_mediador_id"] = cargo.id; await i.response.send_message("✅", ephemeral=True)

@bot.tree.command(name="configurar_canais_filas", description="Canal Tickets")
async def cfg_c(i: discord.Interaction, canal: discord.TextChannel):
    if i.user.id == DONO_ID: configuracao["canais"]["Filas"] = [canal]; await i.response.send_message("✅", ephemeral=True)

@bot.tree.command(name="filamediador", description="Painel Mediador")
async def filamediador(i: discord.Interaction):
    if i.user.id == DONO_ID:
        embed = discord.Embed(title="Painel da fila controladora", description="**Entre na fila para começar a mediar suas filas**", color=discord.Color.purple())
        await i.channel.send(embed=embed, view=MediadorQueueView()); await i.response.send_message("✅", ephemeral=True)

@bot.event
async def on_message(message):
    if message.is_system() and isinstance(message.channel, discord.Thread):
        try: await message.delete()
        except: pass
    await bot.process_commands(message)

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ Bot Online: {bot.user}")

if TOKEN:
    bot.run(TOKEN)
            
