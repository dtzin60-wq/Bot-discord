import discord
import os
import asyncio
import datetime
import traceback
from discord.ext import commands
from discord import app_commands

TOKEN = os.getenv("DISCORD_TOKEN")
DONO_ID = 1461858587080130663

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

configuracao = {
    "cargos": {"ver": [], "finalizar": []},
    "canais": {"Suporte": None, "Reembolso": None, "Receber Evento": None, "Vagas de Mediador": None}
}

class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Finalizar ticket", style=discord.ButtonStyle.success, emoji="✅", custom_id="btn_finalizar_v3")
    async def finalizar(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            cargos_finalizar = configuracao["cargos"].get("finalizar", [])
            user = interaction.user
            e_staff = user.id == DONO_ID or user.guild_permissions.administrator
            if not e_staff and cargos_finalizar:
                for cargo in cargos_finalizar:
                    if cargo in user.roles:
                        e_staff = True
                        break
            if not cargos_finalizar and user.guild_permissions.administrator:
                e_staff = True
            if e_staff:
                await interaction.response.send_message("🚨 **Fechando em 5s...**", ephemeral=True)
                await asyncio.sleep(5)
                if interaction.channel: await interaction.channel.delete()
            else:
                await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)
        except Exception as e:
            print(f"Erro finalizar: {e}")

    @discord.ui.button(label="Assumir Ticket", style=discord.ButtonStyle.secondary, emoji="🛡️", custom_id="btn_assumir_v3")
    async def assumir(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.channel.send(f"🛡️ {interaction.user.mention} assumiu este atendimento!")
        await interaction.response.send_message("Assumido!", ephemeral=True)

    @discord.ui.button(label="Painel Staff", style=discord.ButtonStyle.secondary, emoji="🛠️", custom_id="btn_staff_v3")
    async def staff(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🛠️ Em breve.", ephemeral=True)

    @discord.ui.button(label="Sair Ticket", style=discord.ButtonStyle.danger, emoji="✖️", custom_id="btn_sair_v3")
    async def sair(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.channel.remove_user(interaction.user)
            await interaction.response.send_message("👋 Saiu.", ephemeral=True)
        except:
            await interaction.response.send_message("❌ Erro ao remover usuário.", ephemeral=True)

class TicketDropdown(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Suporte", emoji="🛠️", description="Suporte geral"),
            discord.SelectOption(label="Reembolso", emoji="💰", description="Problemas de pagamento"),
            discord.SelectOption(label="Receber Evento", emoji="💫", description="Resgatar prêmios"),
            discord.SelectOption(label="Vagas de Mediador", emoji="👑", description="Recrutamento"),
        ]
        super().__init__(placeholder="Selecione uma função", options=options, custom_id="select_menu_v3")

    async def callback(self, interaction: discord.Interaction):
        try:
            escolha = self.values[0]
            canal_destino = configuracao["canais"].get(escolha)
            if not canal_destino:
                await interaction.response.send_message(f"⚠️ Erro: Canal para **{escolha}** não configurado. Use `/configurar_topicos`.", ephemeral=True)
                return
            thread = await canal_destino.create_thread(name=f"{escolha}-{interaction.user.name}", type=discord.ChannelType.private_thread, invitable=False)
            await thread.add_user(interaction.user)
            view_jump = discord.ui.View()
            view_jump.add_item(discord.ui.Button(label="Ir para o Ticket", url=thread.jump_url, emoji="🔗"))
            await interaction.response.send_message(content="✅ Ticket criado!", view=view_jump, ephemeral=True)
            embed = discord.Embed(description="Aguarde o atendimento.", color=discord.Color.blue())
            embed.add_field(name="Horário:", value=f"<t:{int(datetime.datetime.now().timestamp())}:F>")
            mencao = f"{interaction.user.mention}"
            for c in configuracao["cargos"].get("ver", []): mencao += f" {c.mention}"
            for c in configuracao["cargos"].get("finalizar", []):
                if c not in configuracao["cargos"].get("ver", []): mencao += f" {c.mention}"
            await thread.send(content=mencao, embed=embed, view=TicketControlView())
        except Exception as e:
            print(f"Erro ao criar ticket: {e}")
            try: await interaction.response.send_message(f"❌ Erro: {e}", ephemeral=True)
            except: pass

class MainView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketDropdown())

@bot.event
async def on_ready():
    print(f"✅ Bot Online: {bot.user}")
    bot.add_view(MainView())
    bot.add_view(TicketControlView())
    await bot.tree.sync()

@bot.tree.command(name="configurar_topicos", description="Define os canais de cada ticket")
async def configurar_topicos(interaction: discord.Interaction, canal_suporte: discord.TextChannel, canal_reembolso: discord.TextChannel, canal_evento: discord.TextChannel, canal_vagas: discord.TextChannel):
    if interaction.user.id != DONO_ID: return await interaction.response.send_message("❌ Apenas o dono.", ephemeral=True)
    configuracao["canais"].update({"Suporte": canal_suporte, "Reembolso": canal_reembolso, "Receber Evento": canal_evento, "Vagas de Mediador": canal_vagas})
    await interaction.response.send_message("✅ Canais salvos!", ephemeral=True)

@bot.tree.command(name="criar_painel", description="Cria o painel (com detector de erro)")
@app_commands.describe(
    staff_1="Cargo Suporte", finalizar_1="Cargo Finalizar",
    staff_2="[Opcional]", staff_3="[Opcional]", staff_4="[Opcional]",
    finalizar_2="[Opcional]", finalizar_3="[Opcional]", finalizar_4="[Opcional]"
)
async def criar_painel(interaction: discord.Interaction, staff_1: discord.Role, finalizar_1: discord.Role, staff_2: discord.Role = None, staff_3: discord.Role = None, staff_4: discord.Role = None, finalizar_2: discord.Role = None, finalizar_3: discord.Role = None, finalizar_4: discord.Role = None):
    await interaction.response.defer(ephemeral=True)
    try:
        if interaction.user.id != DONO_ID:
            return await interaction.followup.send("❌ Apenas o dono pode usar isso.")
        c_ver = [c for c in [staff_1, staff_2, staff_3, staff_4] if c]
        c_fin = [c for c in [finalizar_1, finalizar_2, finalizar_3, finalizar_4] if c]
        configuracao["cargos"]["ver"] = c_ver
        configuracao["cargos"]["finalizar"] = c_fin
        descricao = (
            "👉 Abra ticket com o que você precisa abaixo com as informações de guia.\n\n"
            "☞ **TICKET SUPORTE**\n"
            "tire suas dúvidas aqui no ticket suporte, fale com nossos suportes e seja direto com o seu problema.\n\n"
            "☞ **TICKET REEMBOLSO**\n"
            "receba seu reembolso aqui, seja direto e mande comprovante do pagamento.\n\n"
            "☞ **TICKET RECEBE EVENTO**\n"
            "Receba seu evento completos, espera nossos suportes válida seu evento.\n\n"
            "☞ **TICKET VAGA MEDIADOR**\n"
            "seja mediador da org SPACE, abra ticket e espera nossos suportes recruta.\n\n"
            "→ Evite discussões!"
        )
        # AQUI ESTÁ A MUDANÇA: color=discord.Color.blue()
        embed = discord.Embed(title="WS TICKET", description=descricao, color=discord.Color.blue())
        embed.set_image(url="https://cdn.discordapp.com/attachments/1465403221936963655/1465775330999533773/file_00000000d78871f596a846e9ca08d27c.jpg?ex=6990bea7&is=698f6d27&hm=ab8e0065381fdebb51ecddda1fe599a7366aa8dfe622cfeb7f720b7fadedd896&")
        try:
            await interaction.channel.send(embed=embed, view=MainView())
        except discord.Forbidden:
            raise Exception("O Bot não tem permissão de 'Enviar Mensagens' ou 'Links' neste canal!")
        await interaction.followup.send(f"✅ Painel enviado com sucesso!", ephemeral=True)
    except Exception as e:
        traceback.print_exc()
        await interaction.followup.send(f"❌ **Ocorreu um erro:**\n`{str(e)}`\n\nVerifique se o bot tem permissão de Administrador e se a imagem é válida.", ephemeral=True)

if TOKEN: bot.run(TOKEN)
            
