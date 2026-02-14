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
    # Armazena: {user_id: {"nome": "Fulano", "chave": "Pix", "qrcode": "Link"}}
    "dados_mediadores": {} 
}
tickets_abertos = []
mediadores_ativos = [] # Lista de IDs [id1, id2...]

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
        # Permite Staff, Dono ou quem tem o cargo de mediador configurado
        perm_med = False
        if configuracao["cargo_mediador_id"]:
            role = interaction.guild.get_role(configuracao["cargo_mediador_id"])
            if role in interaction.user.roles: perm_med = True

        if interaction.user.guild_permissions.manage_messages or interaction.user.id == DONO_ID or perm_med:
            await interaction.response.send_message(f"✅ **Pagamento Validado por {interaction.user.mention}!**", ephemeral=False)
        else:
            await interaction.response.send_message("❌ Apenas o Mediador ou Staff.", ephemeral=True)

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
            # --- FASE FINAL: TODOS CONFIRMARAM ---
            
            # 1. Rotação do Mediador
            dados_pix = None
            mediador_txt = "Sem Mediador Online"
            
            if mediadores_ativos:
                # Pega o primeiro e rotaciona
                mediador_id = mediadores_ativos.pop(0)
                mediadores_ativos.append(mediador_id)
                
                # Busca dados cadastrados
                dados = configuracao["dados_mediadores"].get(mediador_id)
                if dados:
                    dados_pix = dados
                    mediador_txt = f"<@{mediador_id}>"
            
            # Se não tiver mediador, usa dados de fallback (Dono) ou avisa erro
            if not dados_pix:
                # Fallback genérico se a fila estiver vazia
                dados_pix = {
                    "nome": "Admin (Sem mediador)",
                    "chave": "Chave Admin",
                    "qrcode": "https://cdn.discordapp.com/attachments/1465403221936963655/1465775330999533773/file_00000000d78871f596a846e9ca08d27c.jpg"
                }

            # 2. Renomear e Limpar Chat
            configuracao["contador_salas"] += 1
            num = configuracao["contador_salas"]
            tipo = "emulador" if "emulador" in self.modo.lower() else "mobile"
            await interaction.channel.edit(name=f"{tipo}-{num}")
            await interaction.channel.purge(limit=100)

            # 3. Painel Confirmado
            embed_final = discord.Embed(title="Partida Confirmada", color=discord.Color.blue())
            embed_final.set_thumbnail(url="https://cdn.discordapp.com/attachments/1465403221936963655/1465775330999533773/file_00000000d78871f596a846e9ca08d27c.jpg")
            embed_final.add_field(name="🎮 Estilo de Jogo", value=self.modo, inline=False)
            embed_final.add_field(name="ℹ️ Informações da Aposta", value=f"Valor Da Sala: {self.valor}\nMediador: {mediador_txt}", inline=False)
            embed_final.add_field(name="💸 Valor da Aposta", value=self.valor, inline=False)
            
            lista_jogs = "\n".join([f"<@{uid}>" for uid in self.jogadores])
            embed_final.add_field(name="👥 Jogadores", value=lista_jogs, inline=False)
            await interaction.channel.send(embed=embed_final)

            # 4. Envia Dados do PIX (Do Mediador da Vez)
            msg_pix = (
                f"**{dados_pix['nome']}**\n"
                f"{dados_pix['chave']}\n"
                f"↪ Valor a pagar: {self.valor}"
            )
            
            embed_qr = discord.Embed(color=discord.Color.dark_theme())
            embed_qr.set_image(url=dados_pix['qrcode']) 
            
            await interaction.channel.send(embed=embed_qr)
            await interaction.channel.send(content=msg_pix, view=PainelPagamentoView())

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.success, custom_id="btn_conf")
    async def confirmar(self, interaction, button):
        if interaction.user.id not in self.jogadores: return await interaction.response.send_message("❌ Não está na partida.", ephemeral=True)
        if interaction.user.id in self.confirmados: return await interaction.response.send_message("✅ Já confirmou.", ephemeral=True)
        self.confirmados.append(interaction.user.id)
        
        embed = interaction.message.embeds[0]
        novos_txt = ""
        for uid in self.jogadores:
            status = "✅" if uid in self.confirmados else "⏳"
            novos_txt += f"{status} <@{uid}>\n"
        embed.set_field_at(2, name="⚡ Jogadores:", value=novos_txt, inline=False)
        
        await interaction.response.defer()
        await interaction.message.edit(embed=embed)
        await self.atualizar_status(interaction)

    @discord.ui.button(label="Recusar", style=discord.ButtonStyle.danger, custom_id="btn_recus")
    async def recusar(self, interaction, button):
        if interaction.user.id not in self.jogadores: return
        await interaction.channel.send(f"❌ **{interaction.user.display_name}** recusou. Cancelando...")
        await asyncio.sleep(3)
        await interaction.channel.delete()

    @discord.ui.button(label="Combinar Regras", style=discord.ButtonStyle.secondary, emoji="🏳️", custom_id="btn_regras")
    async def regras(self, interaction, button):
        await interaction.response.send_message(f"📢 {interaction.user.mention} quer combinar regras!", ephemeral=False)

# ==============================================================================
# 2. SISTEMA DE LOBBY
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
        if self.limite == 2:
            self.add_item(discord.ui.Button(label="Gel Normal", style=discord.ButtonStyle.secondary, custom_id="join_normal"))
            self.add_item(discord.ui.Button(label="Gel Infinito", style=discord.ButtonStyle.secondary, custom_id="join_infinito"))
        else:
            self.add_item(discord.ui.Button(label="Entrar na fila", style=discord.ButtonStyle.secondary, custom_id="join_geral"))
        self.add_item(discord.ui.Button(label="Sair da Fila", style=discord.ButtonStyle.danger, custom_id="leave_fila"))

    async def atualizar_embed(self, interaction):
        texto = "Nenhum jogador na fila" if not self.jogadores else "".join([f"<@{uid}> | {self.dados_visuais.get(uid,'Entrou')}\n" for uid in self.jogadores])
        embed = interaction.message.embeds[0]
        embed.set_field_at(2, name="👥 | Jogadores", value=texto, inline=False)
        await interaction.message.edit(embed=embed, view=self)

    async def iniciar_confirmacao(self, interaction):
        canais = configuracao["canais"].get("Filas", [])
        canal_destino = random.choice(canais) if canais else interaction.channel
        thread = await canal_destino.create_thread(name="aguardando-confirmacao", type=discord.ChannelType.private_thread)
        
        mencoes = ""
        objs_jogadores = []
        for uid in self.jogadores:
            u = interaction.guild.get_member(uid)
            if u:
                await thread.add_user(u)
                mencoes += f"{u.mention} "
                objs_jogadores.append(u)
                tickets_abertos.append(uid)
        
        embed_welcome = discord.Embed(title="✨ SEJAM MUITO BEM-VINDOS ✨", description="• Regras adicionais podem ser combinadas.\n• Obrigatório print do acordo.", color=discord.Color.gold())
        await thread.send(content=mencoes, embed=embed_welcome)

        embed_conf = discord.Embed(title="Aguardando Confirmações", color=discord.Color.dark_grey())
        embed_conf.set_thumbnail(url="https://cdn.discordapp.com/attachments/1465403221936963655/1465775330999533773/file_00000000d78871f596a846e9ca08d27c.jpg")
        embed_conf.add_field(name="👑 Modo:", value=self.modo, inline=False)
        embed_conf.add_field(name="💸 Valor da aposta:", value=self.valor, inline=False)
        lista_inicial = "".join([f"⏳ {u.mention}\n" for u in objs_jogadores])
        embed_conf.add_field(name="⚡ Jogadores:", value=lista_inicial, inline=False)
        
        await thread.send(embed=embed_conf, view=PartidaConfirmacaoView(self.jogadores, self.modo, self.valor))
        
        self.jogadores = []
        self.dados_visuais = {}
        await self.atualizar_embed(interaction)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        cid, uid = interaction.data["custom_id"], interaction.user.id
        if cid == "leave_fila":
            if uid in self.jogadores:
                self.jogadores.remove(uid); del self.dados_visuais[uid]
                await interaction.response.defer(); await self.atualizar_embed(interaction)
            else: await interaction.response.send_message("❌ Não está na fila.", ephemeral=True)
            return True

        if uid in self.jogadores: return await interaction.response.send_message("❌ Já está na fila!", ephemeral=True)
        if len(self.jogadores) >= self.limite: return await interaction.response.send_message("❌ Fila cheia!", ephemeral=True)

        escolha = "Gel Normal" if cid == "join_normal" else "Gel Infinito" if cid == "join_infinito" else "Entrou"
        self.jogadores.append(uid); self.dados_visuais[uid] = escolha
        await interaction.response.defer(); await self.atualizar_embed(interaction)
        if len(self.jogadores) >= self.limite: await self.iniciar_confirmacao(interaction)
        return True

# ==============================================================================
# 3. CRIAÇÃO DE FILAS
# ==============================================================================

class CriarFilasEmMassaModal(discord.ui.Modal, title="Criar Filas (Até 15)"):
    nome = discord.ui.TextInput(label="Nome", placeholder="Ex: 1v1 Mobile")
    valores = discord.ui.TextInput(label="Valores, só pode até 15 filas!", placeholder="Ex: 1,00, 2,00, 5,00", style=discord.TextStyle.paragraph)

    async def on_submit(self, interaction: discord.Interaction):
        lista_valores = [v.strip() for v in self.valores.value.split(",") if v.strip()]
        if len(lista_valores) > 15: return await interaction.response.send_message("❌ Limite de 15 filas.", ephemeral=True)
        
        await interaction.response.send_message(f"✅ Criando {len(lista_valores)} filas...", ephemeral=True)
        
        for val in lista_valores:
            v_fmt = val if "R$" in val else f"R$ {val}"
            embed = discord.Embed(title=f"{self.nome.value} | WS APOSTAS", color=discord.Color.blue())
            embed.add_field(name="👑 | Modo", value=self.nome.value, inline=False)
            embed.add_field(name="💸 | Valor", value=v_fmt, inline=False)
            embed.add_field(name="👥 | Jogadores", value="Nenhum jogador na fila", inline=False)
            embed.set_image(url="https://cdn.discordapp.com/attachments/1465403221936963655/1465775330999533773/file_00000000d78871f596a846e9ca08d27c.jpg")
            await interaction.channel.send(embed=embed, view=FilaLobbyView(self.nome.value, v_fmt, 2)) # Padrão 2 (1v1)
            await asyncio.sleep(1)

# ==============================================================================
# 4. MEDIADOR (CADASTRO E ROTAÇÃO)
# ==============================================================================

class CadastroPixModal(discord.ui.Modal, title="Cadastrar Pix (Mediador)"):
    nome = discord.ui.TextInput(label="Nome do Titular", placeholder="Ex: João da Silva")
    chave = discord.ui.TextInput(label="Chave Pix", placeholder="CPF, Email ou Aleatória")
    qrcode = discord.ui.TextInput(label="Link do QR Code", placeholder="https://imgur.com/...", style=discord.TextStyle.paragraph)

    async def on_submit(self, interaction: discord.Interaction):
        # Salva dados
        configuracao["dados_mediadores"][interaction.user.id] = {
            "nome": self.nome.value,
            "chave": self.chave.value,
            "qrcode": self.qrcode.value
        }
        await interaction.response.send_message("✅ PIX Cadastrado com sucesso! Agora você pode entrar na fila.", ephemeral=True)

class RemoverMediadorModal(discord.ui.Modal, title="Remover Mediador"):
    user_id = discord.ui.TextInput(label="ID")
    async def on_submit(self, i):
        try:
            uid = int(self.user_id.value)
            if uid in mediadores_ativos: mediadores_ativos.remove(uid); await MediadorQueueView().atualizar_embed(i); await i.followup.send(f"✅ Removido <@{uid}>", ephemeral=True)
            else: await i.response.send_message("❌ Não encontrado.", ephemeral=True)
        except: await i.response.send_message("❌ Erro.", ephemeral=True)

class MediadorQueueView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(label="Entrar na fila", style=discord.ButtonStyle.success, emoji="🟢", custom_id="med_join"))
        self.add_item(discord.ui.Button(label="Sair da fila", style=discord.ButtonStyle.danger, emoji="🔴", custom_id="med_leave"))
        self.add_item(discord.ui.Button(label="Remover Mediador", style=discord.ButtonStyle.secondary, emoji="⚙️", custom_id="med_kick"))
        self.add_item(discord.ui.Button(label="Painel Staff", style=discord.ButtonStyle.secondary, emoji="⚙️", custom_id="med_staff"))
    
    async def enviar_confirmacao(self, interaction, entrou: bool):
        embed = discord.Embed(description=f"✅ **Ação realizada com sucesso!**\n\n{interaction.user.mention}, a sua operação foi concluída com êxito.\n↪ Você {'entrou na' if entrou else 'saiu da'} fila com sucesso.", color=discord.Color.from_rgb(43, 45, 49))
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def atualizar_embed(self, interaction):
        txt = "Nenhum mediador na fila." if not mediadores_ativos else "".join([f"**{i}** • <@{uid}> `{uid}`\n" for i, uid in enumerate(mediadores_ativos, 1)])
        embed = interaction.message.embeds[0]
        embed.description = f"**Entre na fila para começar a mediar suas filas**\n\n{txt}"
        if interaction.response.is_done(): await interaction.message.edit(embed=embed, view=self)
        else: await interaction.response.edit_message(embed=embed, view=self)

    async def interaction_check(self, i):
        cid, uid = i.data["custom_id"], i.user.id
        if cid == "med_join":
            # 1. Checa Cargo
            if configuracao["cargo_mediador_id"]:
                r = i.guild.get_role(configuracao["cargo_mediador_id"])
                if r and r not in i.user.roles: return await i.response.send_message("❌ Sem permissão de Mediador.", ephemeral=True)
            
            # 2. Checa Cadastro PIX
            if uid not in configuracao["dados_mediadores"]:
                return await i.response.send_message("❌ Você precisa cadastrar seu PIX primeiro! Use o comando `/cadastrar_pix`.", ephemeral=True)
            
            # 3. Entra na fila
            if uid in mediadores_ativos: await i.response.send_message("❌ Já está na fila.", ephemeral=True)
            else: mediadores_ativos.append(uid); await self.enviar_confirmacao(i, True); await self.atualizar_embed(i)

        elif cid == "med_leave":
            if uid in mediadores_ativos: mediadores_ativos.remove(uid); await self.enviar_confirmacao(i, False); await self.atualizar_embed(i)
            else: await i.response.send_message("❌ Não está na fila.", ephemeral=True)
        elif cid == "med_kick":
            if i.user.id == DONO_ID: await i.response.send_modal(RemoverMediadorModal())
            else: await i.response.send_message("❌ Apenas Dono.", ephemeral=True)
        
        return False

# ==============================================================================
# 5. COMANDOS
# ==============================================================================

@bot.tree.command(name="cadastrar_pix", description="Cadastra suas informações de pagamento (Mediador)")
async def cadastrar_pix(i: discord.Interaction):
    await i.response.send_modal(CadastroPixModal())

@bot.tree.command(name="quem_pode_entrar_na_fila_de_mediador", description="Define cargo permitido na fila")
async def quem_pode(i: discord.Interaction, cargo: discord.Role):
    if i.user.id != DONO_ID: return await i.response.send_message("❌ Apenas dono.", ephemeral=True)
    configuracao["cargo_mediador_id"] = cargo.id
    await i.response.send_message(f"✅ Permissão definida para: {cargo.mention}", ephemeral=True)

@bot.tree.command(name="criar_filas", description="Cria várias filas de uma vez")
async def criar_filas(i: discord.Interaction):
    if i.user.id != DONO_ID: return
    await i.response.send_modal(CriarFilasEmMassaModal())

@bot.tree.command(name="filamediador", description="Painel Mediador")
async def filamediador(i: discord.Interaction):
    if i.user.id != DONO_ID: return
    embed = discord.Embed(title="Painel da fila controladora", description="**Entre na fila para começar a mediar suas filas**\n\nNenhum mediador na fila.", color=discord.Color.purple()) 
    await i.channel.send(embed=embed, view=MediadorQueueView())
    await i.response.send_message("✅", ephemeral=True)

@bot.tree.command(name="configurar_canais_filas", description="Canais de Aposta")
async def cfg_f(i: discord.Interaction, c1: discord.TextChannel, c2: discord.TextChannel=None, c3: discord.TextChannel=None):
    if i.user.id != DONO_ID: return
    l = [c for c in [c1, c2, c3] if c]
    configuracao["canais"]["Filas"] = l
    await i.response.send_message("✅ Configurado.", ephemeral=True)

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
