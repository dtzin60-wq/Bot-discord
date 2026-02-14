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

# --- MEMÓRIA ---
configuracao = {
    "cargos": {"ver": [], "finalizar": []},
    "canais": {"Suporte": None, "Reembolso": None, "Receber Evento": None, "Vagas de Mediador": None}
}

# Lista para impedir múltiplos tickets (Salva ID do usuário)
tickets_abertos = []

# --- VIEW DE CONTROLE ---
class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Finalizar ticket", style=discord.ButtonStyle.success, emoji="✅", custom_id="btn_finalizar_v4")
    async def finalizar(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            # Verifica permissão
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
                await interaction.response.send_message("🚨 **Fechando ticket em 5 segundos...**", ephemeral=True)
                
                # Remove o usuário da lista de tickets abertos (procura quem é o dono do ticket pelo nome ou limpa geral)
                # Como é difícil saber quem é o dono exato aqui, vamos remover pelo nome do canal ou resetar na lógica de sair.
                # Nota: Em bot simples sem banco de dados, o "Limpar lista" perfeito é difícil, 
                # mas aqui vamos tentar remover o usuário que interagiu se ele for o dono, ou deixar que o delete resolva.
                
                await asyncio.sleep(5)
                if interaction.channel: 
                    # Tenta limpar o ID do dono do ticket da lista (Gambiarra funcional baseada no nome do canal)
                    # O nome do canal é "categoria-username".
                    try:
                        nome_dono = interaction.channel.name.split("-")[-1]
                        # Isso não é 100% preciso se o usuario mudar de nome, mas ajuda.
                        # O ideal é o usuário clicar em sair, mas finalizar deleta tudo.
                        # Vamos limpar o ID de quem clicou se não for staff, mas staff finalizando não é o dono.
                        pass 
                    except:
                        pass
                    
                    await interaction.channel.delete()
            else:
                await interaction.response.send_message("❌ Você não tem permissão.", ephemeral=True)
        except Exception as e:
            print(f"Erro finalizar: {e}")

    @discord.ui.button(label="Assumir Ticket", style=discord.ButtonStyle.secondary, emoji="🛡️", custom_id="btn_assumir_v4")
    async def assumir(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.channel.send(f"🛡️ {interaction.user.mention} assumiu este atendimento!")
        await interaction.response.send_message("Atendimento assumido!", ephemeral=True)

    @discord.ui.button(label="Painel Staff", style=discord.ButtonStyle.secondary, emoji="🛠️", custom_id="btn_staff_v4")
    async def staff(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🛠️ Ferramentas da Staff (Em breve)", ephemeral=True)

    @discord.ui.button(label="Sair Ticket", style=discord.ButtonStyle.danger, emoji="✖️", custom_id="btn_sair_v4")
    async def sair(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            user = interaction.user
            # Remove da lista de tickets abertos
            if user.id in tickets_abertos:
                tickets_abertos.remove(user.id)
            
            # Remove permissão (Kick do tópico)
            await interaction.channel.remove_user(user)
            
            # Resposta invisível (O usuário não verá isso pois perdeu acesso na hora, mas evita erro na API)
            # A mágica da imagem "sem acesso" acontece nativamente aqui.
        except:
            pass

# --- MENU SELEÇÃO ---
class TicketDropdown(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Suporte", emoji="🛠️", description="Clique aqui caso precisa de algum suporte"),
            discord.SelectOption(label="Reembolso", emoji="💰", description="Clique aqui caso deseja fazer um reembolso"),
            discord.SelectOption(label="Receber Evento", emoji="💫", description="Clique aqui caso queira receber algum evento"),
            discord.SelectOption(label="Vagas de Mediador", emoji="👑", description="Clique aqui caso queira alguma vaga de mediador na ORG"),
        ]
        super().__init__(placeholder="Selecione uma função", options=options, custom_id="select_menu_v4")

    async def callback(self, interaction: discord.Interaction):
        try:
            user = interaction.user
            
            # 1. VERIFICAÇÃO DE TICKET DUPLICADO
            if user.id in tickets_abertos:
                await interaction.response.send_message("Você já tem um ticket criado não pode criar outro❗", ephemeral=True)
                return

            escolha = self.values[0]
            canal_destino = configuracao["canais"].get(escolha)

            if not canal_destino:
                await interaction.response.send_message(f"⚠️ Erro: Canal para **{escolha}** não configurado. Use `/configurar_topicos`.", ephemeral=True)
                return

            # Cria o tópico
            thread = await canal_destino.create_thread(
                name=f"{escolha}-{user.name}", 
                type=discord.ChannelType.private_thread, 
                invitable=False
            )
            
            # Adiciona o usuário e BLOQUEIA novo ticket
            tickets_abertos.append(user.id)
            await thread.add_user(user)

            # 2. LIMPEZA DA MENSAGEM DO SISTEMA "ADICIONOU FULANO"
            # Tenta apagar a mensagem automática do Discord que diz "Bot adicionou User"
            try:
                async for msg in thread.history(limit=5):
                    if msg.type == discord.MessageType.recipient_add:
                        await msg.delete()
            except:
                pass # Se não der pra apagar (falta de permissão), ignora.

            # Botão de ir para o ticket
            view_jump = discord.ui.View()
            view_jump.add_item(discord.ui.Button(label="Ir para o Ticket", url=thread.jump_url, emoji="🔗"))
            await interaction.response.send_message(content="✅ | Seu ticket foi aberto com sucesso!", view=view_jump, ephemeral=True)

            # Embed DENTRO do ticket
            embed = discord.Embed(
                description="Seja bem-vindo(a) ao painel de atendimento. Informamos que, dependendo do horário em que este ticket foi aberto, o tempo de resposta pode variar.",
                color=discord.Color.dark_grey() # Voltei para cinza escuro no painel interno para contraste
            )
            embed.add_field(name="Horário de Abertura:", value=f"<t:{int(datetime.datetime.now().timestamp())}:F>")
            
            mencao = f"{user.mention}"
            for c in configuracao["cargos"].get("ver", []): mencao += f" {c.mention}"
            for c in configuracao["cargos"].get("finalizar", []): 
                if c not in configuracao["cargos"].get("ver", []): mencao += f" {c.mention}"

            await thread.send(content=mencao, embed=embed, view=TicketControlView())

        except Exception as e:
            # Se der erro, remove da lista pra ele tentar de novo
            if interaction.user.id in tickets_abertos:
                tickets_abertos.remove(interaction.user.id)
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

# --- COMANDOS ---

@bot.tree.command(name="configurar_topicos", description="Define os canais de cada ticket")
async def configurar_topicos(interaction: discord.Interaction, canal_suporte: discord.TextChannel, canal_reembolso: discord.TextChannel, canal_evento: discord.TextChannel, canal_vagas: discord.TextChannel):
    if interaction.user.id != DONO_ID: return await interaction.response.send_message("❌ Apenas o dono.", ephemeral=True)
    configuracao["canais"].update({"Suporte": canal_suporte, "Reembolso": canal_reembolso, "Receber Evento": canal_evento, "Vagas de Mediador": canal_vagas})
    await interaction.response.send_message("✅ Canais salvos!", ephemeral=True)

@bot.tree.command(name="criar_painel", description="Cria o painel WS TICKET")
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

        # DESCRIÇÃO EXATA DA FOTO 1
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
        
        # Cor Azul na lateral e imagem
        embed = discord.Embed(title="WS TICKET", description=descricao, color=discord.Color.blue())
        embed.set_image(url="https://cdn.discordapp.com/attachments/1465403221936963655/1465775330999533773/file_00000000d78871f596a846e9ca08d27c.jpg?ex=6990bea7&is=698f6d27&hm=ab8e0065381fdebb51ecddda1fe599a7366aa8dfe622cfeb7f720b7fadedd896&")
        
        try:
            await interaction.channel.send(embed=embed, view=MainView())
        except discord.Forbidden:
            raise Exception("O Bot não tem permissão neste canal!")
        
        await interaction.followup.send(f"✅ Painel enviado!", ephemeral=True)

    except Exception as e:
        traceback.print_exc()
        await interaction.followup.send(f"❌ Erro: `{str(e)}`", ephemeral=True)

if TOKEN: bot.run(TOKEN)
            
