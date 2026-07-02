import discord
from discord.ext import commands
from discord import app_commands
import qrcode
import io
import json
import os

TOKEN = "COLOQUE_SEU_TOKEN_AQUI"

CONFIG = {
    "staff_role_id": 0,
    "logs_channel_id": 0,
    "finished_channel_id": 0,
    "ticket_category_id": 0,

    "pix": {
        "type": "",
        "key": "",
        "name": "",
        "message": "Realize o pagamento via PIX."
    },

    "interface": {
        "banner_url": "",
        "finish_logo_url": "",
        "open_message": "Clique abaixo para abrir uma mediação."
    },

    "buttons": {
        "open_color": "green",
        "close_color": "red"
    },

    "taxes": {
        "tax1": 5,
        "tax2": 8,
        "tax3": 12,
        "tax4": 20,
        "tax5": 30,
        "tax6": 50,
        "tax7": 1
    }
}

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

def calculate_tax(value):
    taxes = CONFIG["taxes"]

    if value <= 50:
        return taxes["tax1"]
    elif value <= 100:
        return taxes["tax2"]
    elif value <= 200:
        return taxes["tax3"]
    elif value <= 500:
        return taxes["tax4"]
    elif value <= 700:
        return taxes["tax5"]
    elif value <= 1000:
        return taxes["tax6"]
    else:
        return value * (taxes["tax7"] / 100)


def generate_qr(data):
    qr = qrcode.make(data)
    buffer = io.BytesIO()
    qr.save(buffer, "PNG")
    buffer.seek(0)
    return buffer


def save_config():
    with open("config.json", "w", encoding="utf-8") as f:
        json.dump(CONFIG, f, indent=4)


def load_config():
    global CONFIG

    if os.path.exists("config.json"):
        with open("config.json", "r", encoding="utf-8") as f:
            CONFIG = json.load(f)


load_config()

class ConfigView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Configurar PIX", style=discord.ButtonStyle.success)
    async def pix_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="💰 Configuração PIX",
            description=f"""
Tipo: {CONFIG["pix"]["type"]}
Chave: {CONFIG["pix"]["key"]}
Nome: {CONFIG["pix"]["name"]}
            """,
            color=discord.Color.green()
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )

    @discord.ui.button(label="Configurar Taxas", style=discord.ButtonStyle.primary)
    async def tax_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        taxes = CONFIG["taxes"]

        embed = discord.Embed(
            title="📈 Taxas Configuradas",
            description=f"""
Taxa 1: {taxes["tax1"]}
Taxa 2: {taxes["tax2"]}
Taxa 3: {taxes["tax3"]}
Taxa 4: {taxes["tax4"]}
Taxa 5: {taxes["tax5"]}
Taxa 6: {taxes["tax6"]}
Taxa 7: {taxes["tax7"]}%
            """,
            color=discord.Color.blue()
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )

    @discord.ui.button(label="Painel Mediação", style=discord.ButtonStyle.secondary)
    async def panel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="🔒 Sistema Middleman",
            description=CONFIG["interface"]["open_message"],
            color=discord.Color.green()
        )

        await interaction.channel.send(
            embed=embed,
            view=TicketView()
        )

        await interaction.response.send_message(
            "Painel enviado com sucesso.",
            ephemeral=True
        )


@bot.tree.command(name="bot_config", description="Painel de configuração")
async def bot_config(interaction: discord.Interaction):
    embed = discord.Embed(
        title="⚙️ Painel de Configuração",
        description="Use os botões abaixo para configurar o bot.",
        color=discord.Color.green()
    )

    await interaction.response.send_message(
        embed=embed,
        view=ConfigView(),
        ephemeral=True
    )

class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Abrir Intermédio", style=discord.ButtonStyle.success)
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        category = guild.get_channel(CONFIG["ticket_category_id"])

        # Anti-ticket duplicado
        for channel in guild.channels:
            if channel.name == f"ticket-{interaction.user.id}":
                await interaction.response.send_message(
                    "Você já possui um ticket aberto.",
                    ephemeral=True
                )
                return

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True
            )
        }

        if CONFIG["staff_role_id"] != 0:
            staff_role = guild.get_role(CONFIG["staff_role_id"])
            if staff_role:
                overwrites[staff_role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True
                )

        channel = await guild.create_text_channel(
            name=f"ticket-{interaction.user.id}",
            category=category,
            overwrites=overwrites
        )

        embed = discord.Embed(
            title="🎫 Ticket Criado",
            description="""
Sua mediação foi iniciada com sucesso.

Próximos passos:
1 - Escolher usuário mediado
2 - informa valor  
3 - gerar pix
        """,
            color=discord.Color.green()
        )

        await channel.send(
            content=f"{interaction.user.mention}",
            embed=embed
        )

        await interaction.response.send_message(
            f"Ticket criado com sucesso: {channel.mention}",
            ephemeral=True
                        )

 class MemberSelect(discord.ui.Select):
    def __init__(self, members):
        options = []

        for member in members[:25]:
            if not member.bot:
                options.append(
                    discord.SelectOption(
                        label=member.name,
                        value=str(member.id)
                    )
                )

        super().__init__(
            placeholder="Selecione o usuário mediado",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        selected_id = int(self.values[0])
        member = interaction.guild.get_member(selected_id)

        await interaction.channel.set_permissions(
            member,
            view_channel=True,
            send_messages=True
        )

        embed = discord.Embed(
            title="👤 Usuário Selecionado",
            description=f"{member.mention} foi adicionado à mediação.",
            color=discord.Color.blue()
        )

        await interaction.response.send_message(embed=embed)


class MemberView(discord.ui.View):
    def __init__(self, members):
        super().__init__(timeout=None)
        self.add_item(MemberSelect(members)) 

@bot.tree.command(name="finalizar", description="Finalizar mediação")
async def finalizar(interaction: discord.Interaction):
    embed = discord.Embed(
        title="✅ Mediação Finalizada",
        description="Mediação concluída com sucesso.",
        color=discord.Color.green()
    )

    channel = bot.get_channel(CONFIG["finished_channel_id"])
    if channel:
        await channel.send(embed=embed)

    await interaction.response.send_message("Mediação finalizada.")


@bot.tree.command(name="cancelar", description="Cancelar mediação")
async def cancelar(interaction: discord.Interaction):
    embed = discord.Embed(
        title="❌ Mediação Cancelada",
        description="Mediação cancelada.",
        color=discord.Color.red()
    )

    await interaction.channel.send(embed=embed)
    await interaction.response.send_message("Mediação cancelada.")


@bot.tree.command(name="pagar", description="Gerar PIX")
@app_commands.describe(valor="Valor da negociação")
async def pagar(interaction: discord.Interaction, valor: float):
    taxa = calculate_tax(valor)
    total = valor + taxa

    pix_data = f"""
PIX: {CONFIG["pix"]["key"]}
VALOR: R$ {total}
"""

    qr = generate_qr(pix_data)
    file = discord.File(qr, filename="pix.png")

    embed = discord.Embed(
        title="💰 Pagamento PIX",
        color=discord.Color.green()
    )

    embed.add_field(name="Valor", value=f"R$ {valor}", inline=False)
    embed.add_field(name="Taxa", value=f"R$ {taxa}", inline=False)
    embed.add_field(name="Total", value=f"R$ {total}", inline=False)
    embed.set_image(url="attachment://pix.png")

    await interaction.response.send_message(
        embed=embed,
        file=file
    )

@bot.tree.command(name="add", description="Adicionar usuário ao ticket")
@app_commands.describe(usuario="Usuário")
async def add(interaction: discord.Interaction, usuario: discord.Member):
    await interaction.channel.set_permissions(
        usuario,
        view_channel=True,
        send_messages=True
    )

    await interaction.response.send_message(
        f"{usuario.mention} foi adicionado ao ticket."
    )


@bot.tree.command(name="remove", description="Remover usuário do ticket")
@app_commands.describe(usuario="Usuário")
async def remove(interaction: discord.Interaction, usuario: discord.Member):
    await interaction.channel.set_permissions(
        usuario,
        overwrite=None
    )

    await interaction.response.send_message(
        f"{usuario.mention} foi removido do ticket."
    )


@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        print(f"{len(synced)} comandos sincronizados.")
    except Exception as e:
        print(e)

    print(f"Bot online: {bot.user}")


bot.run("MTUyMTkyNzA1MDU2OTU4MDc4NQ.GDgV1s.h077bzqnavOJey3LG1kbOY2CQWGcQw05oxVpWI")
