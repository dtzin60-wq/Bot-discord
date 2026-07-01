import discord
from discord import app_commands
from discord.ext import commands
import os
import random
from flask import Flask
from threading import Thread

# Configuração para manter o bot acordado no Render
app = Flask('')
@app.route('/')
def home():
    return "Bot Online!"

def run():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 3000)))

def keep_alive():
    t = Thread(target=run)
    t.start()

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Banco de dados temporário para armazenar as configurações do painel
config_bot = {
    "banner_abrir": "https://i.imgur.com/link_padrao_abrir.png",
    "banner_encerrar": "https://i.imgur.com/link_padrao_encerrar.png",
    "logo_sucesso": "https://i.imgur.com/link_padrao_logo.png",
    "canal_painel": None,
    "categoria_tickets": None,
    "canal_logs": None
}

dados_tickets = {}

@bot.event
async def on_ready():
    print("Bot de Mediacao online com sucesso!")
    keep_alive()

class MenuUsuarios(discord.ui.UserSelect):
    def __init__(self):
        super().__init__(placeholder="Selecione o usuário com quem você está...", min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        usuario_selecionado = self.values[0]
        await interaction.channel.set_permissions(usuario_selecionado, view_channel=True, send_messages=True)
        
        if interaction.channel.id in dados_tickets:
            dados_tickets[interaction.channel.id]["parceiro"] = usuario_selecionado.mention
            
        await interaction.response.send_message(f"🤝 {usuario_selecionado.mention} foi adicionado com sucesso ao ticket de mediação!", ephemeral=False)

class BotoesTicket(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(MenuUsuarios())

    @discord.ui.button(label="Encerrar Mediação", style=discord.ButtonStyle.secondary, emoji="🗑️", custom_id="encerrar_mediacao")
    async def mantener_encerrar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Finalizando mediação e enviando relatório...", ephemeral=True)
        
        if config_bot["canal_logs"]:
            canal_destino = interaction.guild.get_channel(config_bot["canal_logs"])
            if canal_destino:
                info = dados_tickets.get(interaction.channel.id, {"criador": interaction.user.mention, "parceiro": "Usuário Selecionado"})
                
                embed_sucesso = discord.Embed(title="🦊 Intermediação Manual", color=0xff0000)
                embed_sucesso.set_thumbnail(url=config_bot["logo_sucesso"])
                embed_sucesso.add_field(name="• Nova Intermediação concluída com sucesso!", value=f"Proof #{random.randint(1000, 9000)}", inline=False)
                embed_sucesso.add_field(name="• Valor:", value="R$ 8,00", inline=False)
                embed_sucesso.add_field(name="• Participantes:", value=f"{info['criador']} e {info['parceiro']}", inline=False)
                embed_sucesso.add_field(name="• Administrador:", value=f"{interaction.user.mention}", inline=False)
                
                await canal_destino.send(embed=embed_sucesso)
        
        dados_tickets.pop(interaction.channel.id, None)
        await interaction.channel.delete()

class BotaoAbrir(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Abrir Intermédio", style=discord.ButtonStyle.danger, emoji="🎫", custom_id="abrir_intermedio")
    async def iniciar_abrir(self, interaction: discord.Interaction, button: discord.ui.Button):
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True)
        }
        
        categoria = None
        if config_bot["categoria_tickets"]:
            categoria = interaction.guild.get_channel(config_bot["categoria_tickets"])

        canal_ticket = await interaction.guild.create_text_channel(
            name=f"ticket-{interaction.user.name}",
            overwrites=overwrites,
            category=categoria
        )

        dados_tickets[canal_ticket.id] = {
            "criador": interaction.user.mention,
            "parceiro": "Não selecionado"
        }

        await interaction.response.send_message(
            f"✅ | {interaction.user.mention}, Seu middleman foi aberto **[CLIQUE AQUI](https://discord.com/channels/{interaction.guild.id}/{canal_ticket.id})** para encontrá-lo.",
            ephemeral=True
        )

        embed_ticket = discord.Embed(
            title="Mediação Manual iniciada",
            description=f"{interaction.user.mention}\n\nPedido de Middleman criado com sucesso. Bem-vindo ao nosso sistema de middleman! Seu dinheiro será armazenado com segurança durante toda a negociação...\n\nSelecione no menu abaixo o usuário com quem você está negociando ou insira o ID/menção diretamente na conversa.",
            color=0xff0000
        )
        embed_ticket.set_image(url=config_bot["banner_encerrar"])

        await canal_ticket.send(embed=embed_ticket, view=BotoesTicket())

@bot.tree.command(name="config", description="Configura o menu de intermediação")
async def comando_config(
    interaction: discord.Interaction, 
    banner_abrir: str = None, 
    banner_encerrar: str = None, 
    logo_sucesso: str = None,
    canal_painel: discord.TextChannel = None,
    categoria_tickets: discord.CategoryChannel = None,
    canal_logs: discord.TextChannel = None
):
    if banner_abrir: config_bot["banner_abrir"] = banner_abrir
    if banner_encerrar: config_bot["banner_encerrar"] = banner_encerrar
    if logo_sucesso: config_bot["logo_sucesso"] = logo_sucesso
    if canal_painel: config_bot["canal_painel"] = canal_painel.id
    if categoria_tickets: config_bot["categoria_tickets"] = categoria_tickets.id
    if canal_logs: config_bot["canal_logs"] = canal_logs.id

    await interaction.response.send_message("✅ Configurações de canais e aparência atualizadas com sucesso!", ephemeral=True)

@bot.tree.command(name="painel_mediação", description="Envia o painel principal de mediação")
async def comando_painel(interaction: discord.Interaction):
    canal_id = config_bot["canal_painel"] or interaction.channel_id
    canal_alvo = interaction.guild.get_channel(canal_id)

    embed_inicial = discord.Embed(
        title="🤝 - SOLICITAR MEDIAÇÃO",
        description="🔴 - *Selecione, no menu abaixo, a categoria desejada, oferecemos serviços de intermediação para qualquer tipo de produto ou negociação, sem limitações, garantindo segurança, transparência e agilidade em todo o processo.*",
        color=0xff0000
    )
    embed_inicial.set_image(url=config_bot["banner_abrir"])

    if config_bot["canal_painel"]:
        await canal_alvo.send(embed=embed_inicial, view=BotaoAbrir())
        await interaction.response.send_message(f"✅ Painel enviado no canal {canal_alvo.mention}!", ephemeral=True)
    else:
        await interaction.response.send_message(embed=embed_inicial, view=BotaoAbrir())

@bot.command()
async def registrar_comandos(ctx):
    if ctx.author.id == ctx.guild.owner_id:
        await bot.tree.sync()
        await ctx.send("🚀 Comandos Slash sincronizados com o Discord com sucesso!")

bot.run(os.environ.get('63fa3eaf64930cae6fd01bbb830bd4bf3e752965df643581a9b14e7cbc4f0ec4'))
                
