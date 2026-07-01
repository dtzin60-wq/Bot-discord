import os
import discord
from discord import app_commands
from discord.ext import commands
from flask import Flask
from threading import Thread

# 🌐 1. CONFIGURAÇÃO DO SERVIDOR WEB (Para o Render manter 24/7)
app = Flask('')

@app.route('/')
def home():
    return "Bot de Intermédio Online!"

def run():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

# 🤖 2. CONFIGURAÇÃO PRINCIPAL DO BOT
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

class MiddlemanBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        # Memória temporária para guardar as configurações
        self.config_dados = {
            "banner_abrir": None,
            "banner_encerrar": None,
            "logo_sucesso": None,
            "canal_abrir_id": None,
            "canal_topico_id": None,
            "canal_sucesso_id": None
        }

    async def setup_hook(self):
        # Sincroniza os comandos de barra (/config) automaticamente
        await self.tree.sync()

bot = MiddlemanBot()

# 🛠️ 3. INTERFACES VISUAIS (BOTÕES E TELAS)

# Tela 5: Botão de Encerrar dentro do Tópico de Mediação
class EncerrarView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Encerrar Mediação", style=discord.ButtonStyle.danger, custom_id="btn_encerrar")
    async def encerrar(self, interaction: discord.Interaction, button: discord.ui.Button):
        canal_sucesso_id = bot.config_dados["canal_sucesso_id"]
        logo = bot.config_dados["logo_sucesso"]
        banner_fim = bot.config_dados["banner_encerrar"]

        # Tela 7: Envia logs de sucesso no canal configurado
        if canal_sucesso_id:
            canal_sucesso = bot.get_channel(int(canal_sucesso_id))
            if canal_sucesso:
                embed_sucesso = discord.Embed(
                    title="🤝 Intermédio Finalizado com Sucesso!",
                    description=f"A mediação realizada no tópico **{interaction.channel.name}** foi concluída.",
                    color=discord.Color.green()
                )
                if logo:
                    embed_sucesso.set_thumbnail(url=logo)
                if banner_fim:
                    embed_sucesso.set_image(url=banner_fim)
                
                await canal_sucesso.send(embed=embed_sucesso)

        await interaction.response.send_message("🔒 Este intermédio foi finalizado. O canal será fechado em breve.", ephemeral=True)
        await interaction.channel.delete()

# Tela 4: Menu de seleção de usuários dentro do chat criado
class UsuariosView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.select(cls=discord.ui.UserSelect, placeholder="Selecione os participantes da mediação...", min_values=1, max_values=5)
    async def selecionar_usuarios(self, interaction: discord.Interaction, select: discord.ui.UserSelect):
        usuarios_mencionados = ", ".join([user.mention for user in select.values])
        await interaction.response.send_message(f"👥 **Usuários adicionados ao intermédio:** {usuarios_mencionados}", ephemeral=False)

# Tela 3: Botão de Entrar que aparece no Tópico criado
class EntrarView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Entrar no Intermédio", style=discord.ButtonStyle.success, custom_id="btn_entrar_chat")
    async def entrar_chat(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Tela 4: Exibe o seletor de usuários e o botão de encerrar
        view_painel = discord.ui.View()
        view_painel.add_item(UsuariosView().children[0]) # Adiciona o seletor
        view_painel.add_item(EncerrarView().children[0])  # Adiciona o botão encerrar
        
        await interaction.response.send_message(
            f"👋 Bem-vindo ao suporte de mediação, {interaction.user.mention}! Use o menu abaixo para definir os envolvidos:",
            view=view_painel,
            ephemeral=False
        )

# Tela 1: Botão inicial para "Abrir Intermédio"
class AbrirIntermedioView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Abrir Intermédio", style=discord.ButtonStyle.primary, custom_id="btn_abrir_intermedio")
    async def abrir(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Tela 2: Mensagem efêmera (visível apenas para quem clicou)
        await interaction.response.send_message("⏳ Criando sua sala de mediação privada... Aguarde.", ephemeral=True)

        canal_topico_id = bot.config_dados["canal_topico_id"]
        categoria_alvo = bot.get_channel(int(canal_topico_id)) if canal_topico_id else interaction.channel.category

        # Cria o canal/tópico de texto exclusivo para a mediação
        nome_canal = f"🔴-intermedio-{interaction.user.name}"
        
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            interaction.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }

        novo_canal = await interaction.guild.create_text_channel(
            name=nome_canal,
            category=categoria_alvo if isinstance(categoria_alvo, discord.CategoryChannel) else None,
            overwrites=overwrites
        )

        # Tela 3: Envia a mensagem com o botão "Entrar" no novo canal
        embed_sala = discord.Embed(
            title="🎯 Nova Mediação Iniciada",
            description="Clique no botão abaixo para liberar o painel de gerenciamento do intermédio.",
            color=discord.Color.blue()
        )
        if bot.config_dados["banner_abrir"]:
            embed_sala.set_image(url=bot.config_dados["banner_abrir"])

        await novo_canal.send(embed=embed_sala, view=EntrarView())

# ⚙️ 4. COMANDO DE CONFIGURAÇÃO MODERNA (/config)
@bot.tree.command(name="config", description="Configura os canais, banners e logos do sistema de intermédio.")
@app_commands.describe(
    canal_abrir="Onde ficará a mensagem com o botão de criar intermédio",
    canal_topicos="A categoria ou canal onde as salas de suporte serão abertas",
    canal_sucesso="Onde cairão os logs de intermédios finalizados com sucesso",
    banner_abrir="URL da imagem para o banner de abertura",
    banner_encerrar="URL da imagem para o banner de encerramento",
    logo_sucesso="URL da imagem para a logo de sucesso"
)
async def config(
    interaction: discord.Interaction,
    canal_abrir: discord.TextChannel,
    canal_topicos: discord.TextChannel,
    canal_sucesso: discord.TextChannel,
    banner_abrir: str,
    banner_encerrar: str,
    logo_sucesso: str
):
    # Salva tudo nas variáveis dentro da memória do Bot
    bot.config_dados["canal_abrir_id"] = canal_abrir.id
    bot.config_dados["canal_topico_id"] = canal_topicos.id
    bot.config_dados["canal_sucesso_id"] = canal_sucesso.id
    bot.config_dados["banner_abrir"] = banner_abrir
    bot.config_dados["banner_encerrar"] = banner_encerrar
    bot.config_dados["logo_sucesso"] = logo_sucesso

    await interaction.response.send_message("✅ Configurações salvas na memória com sucesso!", ephemeral=True)

    # Tela 1: Envia automaticamente o painel de abertura no canal escolhido
    embed_inicial = discord.Embed(
        title="💼 Sistema de Intermédio",
        description="Precisa de mediação segura para suas negociações? Clique no botão abaixo para abrir um atendimento privado.",
        color=discord.Color.blue()
    )
    if banner_abrir:
        embed_inicial.set_image(url=banner_abrir)

    await canal_abrir.send(embed=embed_inicial, view=AbrirIntermedioView())

@bot.event
async def on_ready():
    print(f"🤖 Bot conectado com sucesso como: {bot.user.name}")

# 🚀 5. EXECUÇÃO
if __name__ == "__main__":
    keep_alive() # Inicia o Flask para o Render
    
    token = os.environ.get("TOKEN")
    if token is None:
        raise ValueError("ERRO: Variável 'TOKEN' não configurada no Render!")
        
    bot.run("63fa3eaf64930cae6fd01bbb830bd4bf3e752965df643581a9b14e7cbc4f0ec4")
                 
