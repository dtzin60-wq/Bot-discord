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

# --- MEMÓRIA DO SISTEMA ---
configuracao = {
    "cargos": {"ver": [], "finalizar": []},
    "canais": {"Filas": []}, 
    "contador_salas": 0,
    "cargo_mediador_id": None,
    "dados_mediadores": {} # {user_id: {"nome": "...", "chave": "...", "qrcode": "..."}}
}
tickets_abertos = []
mediadores_ativos = [] 

# ==============================================================================
# 1. SISTEMA DE PAGAMENTO E CONFIRMAÇÃO (DINÂMICO)
# ==============================================================================

class PainelPagamentoView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(label="Regras", style=discord.ButtonStyle.secondary, emoji="📄", custom_id="btn_regras_final"))
        self.add_item(discord.ui.Button(label="Menu Mediador", style=discord.ButtonStyle.primary, custom_id="btn_menu_med", row=0))

    @discord.ui.button(label="Validar Pagamento", style=discord.ButtonStyle.success, emoji="💸", custom_id="btn_val_pay", row=1)
    async def validar(self, interaction, button):
        perm_med = False
        if configuracao["cargo_mediador_id"]:
            role = interaction.guild.get_role(configuracao["cargo_mediador_id"])
            if role in interaction.user.roles: perm_med = True

        if interaction.user.guild_permissions.manage_messages or interaction.user.id == DONO_ID or perm_med:
            await interaction.response.send_message(f"✅ **Pagamento Validado por {interaction.user.mention}!**", ephemeral=False)
        else:
            await interaction.response.send_message("❌ Apenas o Mediador da vez ou Staff.", ephemeral=True)

    @discord.ui.button(label="Fechar Sala", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="btn_close_sala", row=1)
    async def fechar(self, interaction, button):
        if interaction.user.guild_permissions.manage_messages or interaction.user.id == DONO_ID:
            await interaction.channel.delete()

class PartidaConfirmacaoView(discord.ui.View):
    def __init__(self, jogadores, modo, valor):
        super().__init__(timeout=None)
        self.jogadores = jogadores
        self.modo = modo
        self.valor = valor
        self.confirmados = []

    async def atualizar_status(self, interaction):
        if len(self.confirmados) >= len(self.jogadores):
            # ROTAÇÃO DE MEDIADOR
            dados_pix = None
            mediador_txt = "Sem Mediador Online"
            
            if mediadores_ativos:
                mediador_id = mediadores_ativos.pop(0)
                mediadores_ativos.append(mediador_id) # Volta pro final da fila
                dados = configuracao["dados_mediadores"].get(mediador_id)
                if dados:
                    dados_pix = dados
                    mediador_txt = f"<@{mediador_id}>"
            
            if not dados_pix:
                dados_pix = {"nome": "Admin", "chave": "Chave Indisponível", "qrcode": "https://cdn.discordapp.com/attachments/1465403221936963655/1465775330999533773/file_00000000d78871f596a846e9ca08d27c.jpg"}

            # LIMPEZA E RENOMEAÇÃO
            configuracao["contador_salas"] += 1
            tipo = "emulador" if "emulador" in self.modo.lower() else "mobile"
            await interaction.channel.edit(name=f"{tipo}-{configuracao['contador_salas']}")
            await interaction.channel.purge(limit=50)

            # PAINEL FINAL
            embed_final = discord.Embed(title="Partida Confirmada", color=discord.Color.blue())
            embed_final.set_thumbnail(url="https://cdn.discordapp.com/attachments/1465403221936963655/1465775330999533773/file_00000000d78871f596a846e9ca08d27c.jpg")
            embed_final.add_field(name="🎮 Estilo de Jogo", value=self.modo, inline=False)
            embed_final.add_field(name="ℹ️ Informações da Aposta", value=f"Valor Da Sala: {self.valor}\nMediador: {mediador_txt}", inline=False)
            embed_final.add_field(name="💸 Valor da Aposta", value=self.valor, inline=False)
            embed_final.add_field(name="👥 Jogadores", value="\n".join([f"<@{u}>" for u in self.jogadores]), inline=False)
            
            await interaction.channel.send(embed=embed_final)
            
            # QR CODE E PIX DO MEDIADOR DA VEZ
            embed_qr = discord.Embed(color=discord.Color.dark_theme())
            embed_qr.set_image(url=dados_pix["qrcode"])
            await interaction.channel.send(embed=embed_qr)
            await interaction.channel.send(content=f"**{dados_pix['nome']}**\n{dados_pix['chave']}\n↪ Valor a pagar: {self.valor}", view=PainelPagamentoView())

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.success, custom_id="btn_conf")
    async def confirmar(self, interaction, button):
        if interaction.user.id not in self.jogadores: return
        if interaction.user.id in self.confirmados: return
        self.confirmados.append(interaction.user.id)
        
        embed = interaction.message.embeds[0]
        novos_txt = "".join([f"{'✅' if u in self.confirmados else '⏳'} <@{u}>\n" for u in self.jogadores])
        embed.set_field_at(2, name="⚡ Jogadores:", value=novos_txt, inline=False)
        
        await interaction.response.defer()
        await interaction.message.edit(embed=embed)
        await self.atualizar_status(interaction)

    @discord.ui.button(label="Recusar", style=discord.ButtonStyle.danger, custom_id="btn_recus")
    async def recusar(self, interaction, button):
        if interaction.user.id in self.jogadores:
            await interaction.channel.send(f"❌ Partida cancelada por {interaction.user.mention}")
            await asyncio.sleep(3)
            await interaction.channel.delete()

# ==============================================================================
# 2. SISTEMA DE LOBBY (FILAS)
# ==============================================================================

class FilaLobbyView(discord.ui.View):
    def __init__(self, modo: str, valor: str, limite: int):
        super().__init__(timeout=None)
        self.limite, self.modo, self.valor = limite, modo, valor
        self.jogadores, self.dados_visuais = [], {}
        self.configurar_botoes()

    def configurar_botoes(self):
        self.clear_items()
        if self.limite == 2:
            self.add_item(discord.ui.Button(label="Gel Normal", style=discord.ButtonStyle.secondary, custom_id="j_norm"))
            self.add_item(discord.ui.Button(label="Gel Infinito", style=discord.ButtonStyle.secondary, custom_id="j_inf"))
        else:
            self.add_item(discord.ui.Button(label="Entrar na fila", style=discord.ButtonStyle.secondary, custom_id="j_geral"))
        self.add_item(discord.ui.Button(label="Sair da Fila", style=discord.ButtonStyle.danger, custom_id="l_fila"))

    async def atualizar_embed(self, interaction):
        texto = "Nenhum jogador na fila" if not self.jogadores else "".join([f"<@{u}> | {self.dados_visuais.get(u,'Entrou')}\n" for u in self.jogadores])
        embed = interaction.message.embeds[0]
        embed.set_field_at(2, name="👥 | Jogadores", value=texto, inline=False)
        await interaction.message.edit(embed=embed, view=self)

    async def iniciar_confirmacao(self, interaction):
        canais = configuracao["canais"].get("Filas", [])
        canal_destino = random.choice(canais) if canais else interaction.channel
        thread = await canal_destino.create_thread(name="aguardando-confirmacao", type=discord.ChannelType.private_thread)
        
        mencoes = "".join([f"<@{u}> " for u in self.jogadores])
        for u in self.jogadores:
            user_obj = interaction.guild.get_member(u)
            if user_obj: await thread.add_user(user_obj)

        embed_welcome = discord.Embed(title="✨ SEJAM MUITO BEM-VINDOS ✨", description="• Regras podem ser combinadas.\n• Obrigatório print do acordo.", color=discord.Color.gold())
        await thread.send(content=mencoes, embed=embed_welcome)

        embed_conf = discord.Embed(title="Aguardando Confirmações", color=discord.Color.dark_grey())
        embed_conf.set_thumbnail(url="https://cdn.discordapp.com/attachments/1465403221936963655/1465775330999533773/file_00000000d78871f596a846e9ca08d27c.jpg")
        embed_conf.add_field(name="👑 Modo:", value=self.modo, inline=False)
        embed_conf.add_field(name="💸 Valor:", value=self.valor, inline=False)
        embed_conf.add_field(name="⚡ Jogadores:", value="".join([f"⏳ <@{u}>\n" for u in self.jogadores]), inline=False)
        
        await thread.send(embed=embed_conf, view=PartidaConfirmacaoView(self.jogadores, self.modo, self.valor))
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
        if len(self.jogadores) >= self.limite: await self.iniciar_confirmacao(i)
        return True

# ==============================================================================
# 3. CRIAÇÃO DE FILAS EM MASSA
# ==============================================================================

class CriarFilasEmMassaModal(discord.ui.Modal, title="Criar Filas (Max 15)"):
    nome = discord.ui.TextInput(label="Nome", placeholder="Ex: 1v1 Mobile")
    valores = discord.ui.TextInput(label="Valores (Separe por vírgula)", placeholder="1,00, 2,00, 5,00", style=discord.TextStyle.paragraph)

    async def on_submit(self, interaction: discord.Interaction):
        lista = [v.strip() for v in self.valores.value.split(",") if v.strip()][:15]
        await interaction.response.send_message(f"✅ Criando {len(lista)} filas...", ephemeral=True)
        for val in lista:
            v_fmt = f"R$ {val}" if "R$" not in val else val
            embed = discord.Embed(title=f"{self.nome.value} | WS APOSTAS", color=discord.Color.blue())
            embed.add_field(name="👑 | Modo", value=self.nome.value, inline=False)
            embed.add_field(name="💸 | Valor", value=v_fmt, inline=False)
            embed.add_field(name="👥 | Jogadores", value="Nenhum jogador na fila", inline=False)
            embed.set_image(url="https://cdn.discordapp.com/attachments/1465403221936963655/1465775330999533773/file_00000000d78871f596a846e9ca08d27c.jpg")
            await interaction.channel.send(embed=embed, view=FilaLobbyView(self.nome.value, v_fmt, 2))
            await asyncio.sleep(1)

# ==============================================================================
# 4. MEDIADORES (CADASTRO E FILA)
# ==============================================================================

class CadastroPixModal(discord.ui.Modal, title="Cadastrar Pix"):
    nome = discord.ui.TextInput(label="Nome Titular")
    chave = discord.ui.TextInput(label="Chave Pix")
    qr = discord.ui.TextInput(label="Link QR Code", style=discord.TextStyle.paragraph)
    async def on_submit(self, i):
        configuracao["dados_mediadores"][i.user.id] = {"nome": self.nome.value, "chave": self.chave.value, "qrcode": self.qr.value}
        await i.response.send_message("✅ PIX Cadastrado!", ephemeral=True)

class MediadorQueueView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    
    async def atualizar_embed(self, i):
        txt = "Nenhum mediador na fila." if not mediadores_ativos else "".join([f"**{idx}** • <@{u}> `{u}`\n" for idx, u in enumerate(mediadores_ativos, 1)])
        embed = i.message.embeds[0]
        embed.description = f"**Entre na fila para começar a mediar suas filas**\n\n{txt}"
        if i.response.is_done(): await i.message.edit(embed=embed)
        else: await i.response.edit_message(embed=embed)

    @discord.ui.button(label="Entrar na fila", style=discord.ButtonStyle.success, emoji="🟢")
    async def entrar(self, i, b):
        if configuracao["cargo_mediador_id"] and not any(r.id == configuracao["cargo_mediador_id"] for r in i.user.roles):
            return await i.response.send_message("❌ Sem permissão.", ephemeral=True)
        if i.user.id not in configuracao["dados_mediadores"]:
            return await i.response.send_message("❌ Use `/cadastrar_pix` primeiro!", ephemeral=True)
        if i.user.id in mediadores_ativos: return
        mediadores_ativos.append(i.user.id)
        await i.response.send_message("✅ Entrou na fila!", ephemeral=True); await self.atualizar_embed(i)

    @discord.ui.button(label="Sair da fila", style=discord.ButtonStyle.danger, emoji="🔴")
    async def sair(self, i, b):
        if i.user.id in mediadores_ativos: mediadores_ativos.remove(i.user.id); await self.atualizar_embed(i)
        await i.response.send_message("✅ Saiu!", ephemeral=True)

# ==============================================================================
# 5. COMANDOS E INICIALIZAÇÃO
# ==============================================================================

@bot.tree.command(name="cadastrar_pix", description="Cadastra dados de pagamento")
async def cadastrar_pix(i: discord.Interaction): await i.response.send_modal(CadastroPixModal())

@bot.tree.command(name="config_cargo_mediador", description="Define cargo permitido")
async def config_cargo_mediador(i: discord.Interaction, cargo: discord.Role):
    if i.user.id == DONO_ID: configuracao["cargo_mediador_id"] = cargo.id; await i.response.send_message("✅ Cargo definido.", ephemeral=True)

@bot.tree.command(name="criar_filas", description="Cria várias filas")
async def criar_filas(i: discord.Interaction):
    if i.user.id == DONO_ID: await i.response.send_modal(CriarFilasEmMassaModal())

@bot.tree.command(name="filamediador", description="Painel Mediador")
async def filamediador(i: discord.Interaction):
    if i.user.id == DONO_ID:
        embed = discord.Embed(title="Painel da fila controladora", description="**Entre na fila para começar a mediar suas filas**\n\nNenhum mediador na fila.", color=discord.Color.purple())
        await i.channel.send(embed=embed, view=MediadorQueueView()); await i.response.send_message("✅", ephemeral=True)

@bot.tree.command(name="configurar_canais_filas", description="Canais de Aposta")
async def cfg_f(i: discord.Interaction, c1: discord.TextChannel):
    if i.user.id == DONO_ID: configuracao["canais"]["Filas"] = [c1]; await i.response.send_message("✅ Configurado.", ephemeral=True)

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
            
