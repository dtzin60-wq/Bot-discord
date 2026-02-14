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
# 1. SISTEMA DE PAGAMENTO E CONFIRMAÇÃO
# ==============================================================================

class PainelPagamentoView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(label="Regras", style=discord.ButtonStyle.secondary, emoji="📄", custom_id="btn_ver_regras"))
        self.add_item(discord.ui.Button(label="Menu Mediador", style=discord.ButtonStyle.primary, custom_id="btn_menu_med", row=0))

    @discord.ui.button(label="Validar Pagamento", style=discord.ButtonStyle.success, emoji="💸", custom_id="btn_val_pay", row=1)
    async def validar(self, interaction, button):
        perm_med = False
        if configuracao["cargo_mediador_id"]:
            role = interaction.guild.get_role(configuracao["cargo_mediador_id"])
            if role and role in interaction.user.roles: perm_med = True

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
            # LÓGICA DE ROTAÇÃO DE MEDIADOR
            dados_pix = None
            mediador_txt = "Sem Mediador Online"
            
            if mediadores_ativos:
                mediador_id = mediadores_ativos.pop(0)
                mediadores_ativos.append(mediador_id) # Volta pro final da fila
                dados = configuracao["dados_mediadores"].get(mediador_id)
                if dados:
                    dados_pix = dados
                    mediador_txt = f"<@{mediador_id}>"
            
            # Fallback (Dados padrão se não tiver mediador)
            if not dados_pix:
                dados_pix = {"nome": "Admin", "chave": "Chave Indisponível", "qrcode": "https://cdn.discordapp.com/attachments/1465403221936963655/1465775330999533773/file_00000000d78871f596a846e9ca08d27c.jpg"}

            # LIMPEZA DO CHAT E RENOMEAÇÃO
            configuracao["contador_salas"] += 1
            num = configuracao["contador_salas"]
            tipo = "emulador" if "emulador" in self.modo.lower() else "mobile"
            await interaction.channel.edit(name=f"{tipo}-{num}")
            await interaction.channel.purge(limit=50)

            # PAINEL FINAL "PARTIDA CONFIRMADA"
            embed_final = discord.Embed(title="Partida Confirmada", color=discord.Color.blue())
            embed_final.set_thumbnail(url="https://cdn.discordapp.com/attachments/1465403221936963655/1465775330999533773/file_00000000d78871f596a846e9ca08d27c.jpg")
            embed_final.add_field(name="🎮 Estilo de Jogo", value=self.modo, inline=False)
            embed_final.add_field(name="ℹ️ Informações da Aposta", value=f"Valor Da Sala: {self.valor}\nMediador: {mediador_txt}", inline=False)
            embed_final.add_field(name="💸 Valor da Aposta", value=self.valor, inline=False)
            embed_final.add_field(name="👥 Jogadores", value="\n".join([f"<@{u}>" for u in self.jogadores]), inline=False)
            await interaction.channel.send(embed=embed_final)

            # ENVIAR QR CODE E PIX
            embed_qr = discord.Embed(color=discord.Color.dark_theme())
            embed_qr.set_image(url=dados_pix["qrcode"]) 
            await interaction.channel.send(embed=embed_qr)
            
            msg_pix = f"**{dados_pix['nome']}**\n{dados_pix['chave']}\n↪ Valor a pagar: {self.valor}"
            await interaction.channel.send(content=msg_pix, view=PainelPagamentoView())

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
        if interaction.user.id not in self.jogadores: return
        await interaction.channel.send(f"❌ Cancelado por {interaction.user.mention}")
        await asyncio.sleep(2)
        await interaction.channel.delete()

    @discord.ui.button(label="Combinar Regras", style=discord.ButtonStyle.secondary, emoji="🏳️", custom_id="btn_regras")
    async def regras(self, interaction, button):
        await interaction.response.send_message(f"📢 {interaction.user.mention} quer combinar regras!", ephemeral=False)

# ==============================================================================
# 2. SISTEMA DE LOBBY (FILAS - SEMPRE 2 JOGADORES)
# ==============================================================================

class FilaLobbyView(discord.ui.View):
    def __init__(self, modo: str, valor: str, limite: int):
        super().__init__(timeout=None)
        self.limite = limite
        self.modo = modo
        self.valor = valor
        self.jogadores = [] 
        self.dados_visuais = {} 
        self.configurar_botoes()

    def configurar_botoes(self):
        self.clear_items()
        # Como o limite agora é SEMPRE 2, sempre mostrará estes botões:
        self.add_item(discord.ui.Button(label="Gel Normal", style=discord.ButtonStyle.secondary, custom_id="j_norm"))
        self.add_item(discord.ui.Button(label="Gel Infinito", style=discord.ButtonStyle.secondary, custom_id="j_inf"))
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
            obj = interaction.guild.get_member(u)
            if obj: await thread.add_user(obj)

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
# 3. CRIAÇÃO DE FILAS (MASSIVA + FORMATAÇÃO)
# ==============================================================================

class CriarFilasEmMassaModal(discord.ui.Modal, title="Criar Filas (Max 15)"):
    nome = discord.ui.TextInput(label="Nome", placeholder="Ex: 1v1 Mobile")
    valores = discord.ui.TextInput(label="Valores (Separe por BARRA /)", placeholder="Ex: 10,00 / 20,00 / 5,00", style=discord.TextStyle.paragraph)

    async def on_submit(self, interaction: discord.Interaction):
        # Separa por BARRA (/)
        lista_raw = [v.strip() for v in self.valores.value.split("/") if v.strip()][:15]
        
        if not lista_raw: return await interaction.response.send_message("❌ Nenhum valor válido.", ephemeral=True)
        
        await interaction.response.send_message(f"✅ Criando {len(lista_raw)} filas...", ephemeral=True)
        
        for val in lista_raw:
            v_limpo = val.replace("R$", "").strip()
            # Formatação de moeda:
            if "," not in v_limpo and "." not in v_limpo:
                v_fmt = f"R$ {v_limpo},00"
            else:
                v_fmt = f"R$ {v_limpo}"

            embed = discord.Embed(title=f"{self.nome.value} | WS APOSTAS", color=discord.Color.blue())
            embed.add_field(name="👑 | Modo", value=self.nome.value, inline=False)
            embed.add_field(name="💸 | Valor", value=v_fmt, inline=False)
            embed.add_field(name="👥 | Jogadores", value="Nenhum jogador na fila", inline=False)
            embed.set_image(url="https://cdn.discordapp.com/attachments/1465403221936963655/1465775330999533773/file_00000000d78871f596a846e9ca08d27c.jpg")
            
            # AQUI ESTÁ A FIXAÇÃO: Limite sempre 2 (1v1)
            await interaction.channel.send(embed=embed, view=FilaLobbyView(self.nome.value, v_fmt, 2))
            await asyncio.sleep(1)

# ==============================================================================
# 4. PAINEL DE CONFIGURAÇÃO DE PIX (ROXO)
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

    @discord.ui.button(label="Chave Pix", style=discord.ButtonStyle.success, emoji="💠", custom_id="btn_cfg_pix")
    async def chave_pix(self, i, b):
        await i.response.send_modal(CadastroPixModal())

    @discord.ui.button(label="Sua Chave", style=discord.ButtonStyle.success, emoji="🔍", custom_id="btn_ver_sua")
    async def sua_chave(self, i, b):
        dados = configuracao["dados_mediadores"].get(i.user.id)
        if not dados: return await i.response.send_message("❌ Você não tem chave cadastrada.", ephemeral=True)
        await i.response.send_message(f"**Sua Chave:**\nNome: {dados['nome']}\nChave: {dados['chave']}\nQR: {dados['qrcode']}", ephemeral=True)

    @discord.ui.button(label="Ver Chave de Mediador", style=discord.ButtonStyle.secondary, emoji="👁️", custom_id="btn_ver_outra")
    async def ver_outra(self, i, b):
        await i.response.send_message("⚠️ Função em desenvolvimento.", ephemeral=True)

# ==============================================================================
# 5. MEDIADORES (FILA E ROTAÇÃO)
# ==============================================================================

class RemoverMediadorModal(discord.ui.Modal, title="Remover ID"):
    uid = discord.ui.TextInput(label="ID")
    async def on_submit(self, i):
        try:
            u = int(self.uid.value)
            if u in mediadores_ativos: mediadores_ativos.remove(u); await MediadorQueueView().atualizar_embed(i); await i.followup.send("✅", ephemeral=True)
        except: pass

class MediadorQueueView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    
    async def atualizar_embed(self, i):
        txt = "Nenhum mediador na fila." if not mediadores_ativos else "".join([f"**{idx+1}** • <@{u}> `{u}`\n" for idx, u in enumerate(mediadores_ativos)])
        embed = i.message.embeds[0]
        embed.description = f"**Entre na fila para começar a mediar suas filas**\n\n{txt}"
        if i.response.is_done(): await i.message.edit(embed=embed)
        else: await i.response.edit_message(embed=embed)

    @discord.ui.button(label="Entrar na fila", style=discord.ButtonStyle.success, emoji="🟢", custom_id="med_join")
    async def entrar(self, i, b):
        if configuracao["cargo_mediador_id"] and not any(r.id == configuracao["cargo_mediador_id"] for r in i.user.roles):
            return await i.response.send_message("❌ Sem permissão.", ephemeral=True)
        if i.user.id not in configuracao["dados_mediadores"]:
            return await i.response.send_message("❌ Cadastre seu PIX primeiro no painel `/cadastrar_pix`!", ephemeral=True)
        if i.user.id in mediadores_ativos: return await i.response.send_message("❌ Já está na fila.", ephemeral=True)
        mediadores_ativos.append(i.user.id)
        await i.response.send_message("✅ Entrou!", ephemeral=True); await self.atualizar_embed(i)

    @discord.ui.button(label="Sair da fila", style=discord.ButtonStyle.danger, emoji="🔴", custom_id="med_leave")
    async def sair(self, i, b):
        if i.user.id in mediadores_ativos: mediadores_ativos.remove(i.user.id); await self.atualizar_embed(i)
        await i.response.send_message("✅ Saiu!", ephemeral=True)

    @discord.ui.button(label="Remover Mediador", style=discord.ButtonStyle.secondary, emoji="⚙️", custom_id="med_kick")
    async def kick(self, i, b):
        if i.user.id == DONO_ID: await i.response.send_modal(RemoverMediadorModal())

    @discord.ui.button(label="Painel Staff", style=discord.ButtonStyle.secondary, emoji="⚙️", custom_id="med_staff")
    async def staff(self, i, b):
        if i.user.guild_permissions.manage_messages: await i.response.send_message("Menu Staff", ephemeral=True)

# ==============================================================================
# 6. COMANDOS SLASH
# ==============================================================================

@bot.tree.command(name="cadastrar_pix", description="Abre painel de configuração de PIX")
async def cadastrar_pix(i: discord.Interaction):
    embed = discord.Embed(title="Painel Para Configurar Chave PIX", description="Gerencie de forma rápida a chave PIX utilizada nas suas filas.\n\nSelecione uma das opções abaixo para cadastrar, visualizar ou editar sua chave PIX.", color=discord.Color.dark_purple())
    embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/1465403221936963655/1465775330999533773/file_00000000d78871f596a846e9ca08d27c.jpg")
    await i.channel.send(embed=embed, view=PainelConfigPixView())
    await i.response.send_message("✅ Painel enviado.", ephemeral=True)

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
                       
