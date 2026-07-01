const { 
    Client, 
    GatewayIntentBits, 
    EmbedBuilder, 
    ActionRowBuilder, 
    ButtonBuilder, 
    ButtonStyle, 
    ChannelType, 
    PermissionFlagsBits, 
    UserSelectMenuBuilder,
    SlashCommandBuilder
} = require('discord.js');

const client = new Client({ 
    intents: [
        GatewayIntentBits.Guilds, 
        GatewayIntentBits.GuildMessages,
        GatewayIntentBits.MessageContent
    ] 
});

// Banco de dados simulado (Em produção, o ideal é usar um arquivo JSON ou Banco de Dados)
let configBot = {
    bannerAbrir: 'https://i.imgur.com/link_padrao_abrir.png',
    bannerEncerrar: 'https://i.imgur.com/link_padrao_encerrar.png',
    logoSucesso: 'https://i.imgur.com/link_padrao_logo.png',
    canalPainel: null,      // Onde fica o botão de abrir intermédio
    categoriaTickets: null, // Onde os canais/tópicos de mediação vão abrir
    canalLogs: null         // Onde cai a mensagem de terminado com sucesso
};

client.once('ready', () => {
    console.log(`🤖 Bot de Mediação online como ${client.user.tag}!`);
    
    // Configuração básica para manter o bot acordado em clouds como o Render
    const express = require('express');
    const app = express();
    app.get('/', (req, res) => res.send('Bot Online!'));
    app.listen(process.env.PORT || 3000);
});

// Comando /config e /painel_mediação
client.on('interactionCreate', async interaction => {
    if (!interaction.isChatInputCommand()) return;

    if (interaction.commandName === 'config') {
        const bannerAbrir = interaction.options.getString('banner_abrir');
        const bannerEncerrar = interaction.options.getString('banner_encerrar');
        const logoSucesso = interaction.options.getString('logo_sucesso');
        const canalPainel = interaction.options.getChannel('canal_painel');
        const categoriaTickets = interaction.options.getChannel('categoria_tickets');
        const canalLogs = interaction.options.getChannel('canal_logs');

        if (bannerAbrir) configBot.bannerAbrir = bannerAbrir;
        if (bannerEncerrar) configBot.bannerEncerrar = bannerEncerrar;
        if (logoSucesso) configBot.logoSucesso = logoSucesso;
        if (canalPainel) configBot.canalPainel = canalPainel.id;
        if (categoriaTickets) configBot.categoriaTickets = categoriaTickets.id;
        if (canalLogs) configBot.canalLogs = canalLogs.id;

        return interaction.reply({ content: '✅ Configurações de canais e aparência atualizadas!', ephemeral: true });
    }

    if (interaction.commandName === 'painel_mediação') {
        // Verifica se o canal do painel foi configurado, se não, envia no canal atual
        const targetChannelId = configBot.canalPainel || interaction.channelId;
        const targetChannel = interaction.guild.channels.cache.get(targetChannelId);

        const embedInicial = new EmbedBuilder()
            .setColor('#ff0000')
            .setTitle('🤝 - SOLICITAR MEDIAÇÃO')
            .setDescription('🔴 - *Selecione, no menu abaixo, a categoria desejada, oferecemos serviços de intermediação para qualquer tipo de produto ou negociação, sem limitações, garantindo segurança, transparência e agilidade em todo o processo.*')
            .setImage(configBot.bannerAbrir);

        const botaoAbrir = new ActionRowBuilder().addComponents(
            new ButtonBuilder()
                .setCustomId('abrir_intermedio')
                .setLabel('Abrir Intermédio')
                .setStyle(ButtonStyle.Danger)
                .setEmoji('🎫')
        );

        if (configBot.canalPainel) {
            await targetChannel.send({ embeds: [embedInicial], components: [botaoAbrir] });
            await interaction.reply({ content: `✅ Painel enviado com sucesso no canal <#${configBot.canalPainel}>!`, ephemeral: true });
        } else {
            await interaction.reply({ embeds: [embedInicial], components: [botaoAbrir] });
        }
    }
});

// Lógica de abertura, botões e encerramento
client.on('interactionCreate', async interaction => {
    if (interaction.isButton()) {
        
        if (interaction.customId === 'abrir_intermedio') {
            await interaction.deferReply({ ephemeral: true });

            // Define as opções do canal de ticket (coloca dentro da categoria se estiver configurada)
            const channelOptions = {
                name: `ticket-${interaction.user.username}`,
                type: ChannelType.GuildText,
                permissionOverwrites: [
                    { id: interaction.guild.id, deny: [PermissionFlagsBits.ViewChannel] },
                    { id: interaction.user.id, allow: [PermissionFlagsBits.ViewChannel, PermissionFlagsBits.SendMessages] },
                ],
            };

            if (configBot.categoriaTickets) {
                channelOptions.parent = configBot.categoriaTickets;
            }

            // Criar canal de ticket/tópico
            const canalTicket = await interaction.guild.channels.create(channelOptions);

            const rowIrParaTicket = new ActionRowBuilder().addComponents(
                new ButtonBuilder()
                    .setLabel('Ir para o ticket')
                    .setURL(`https://discord.com/channels/${interaction.guild.id}/${canalTicket.id}`)
                    .setStyle(ButtonStyle.Link)
            );

            // Resposta apenas para quem clicou (Mensagem efêmera)
            await interaction.editReply({
                content: `✅ | ${interaction.user}, Seu middleman foi aberto **CLIQUE AQUI** para encontrá-lo.`,
                components: [rowIrParaTicket]
            });

            // Mensagem de dentro do Ticket
            const embedTicket = new EmbedBuilder()
                .setColor('#ff0000')
                .setTitle('Mediação Manual iniciada')
                .setDescription(`${interaction.user}\n\nPedido de Middleman criado com sucesso. Bem-vindo ao nosso sistema de middleman! Seu dinheiro será armazenado com segurança durante toda a negociação...\n\nSelecione no menu abaixo o usuário com quem você está negociando ou insira o ID/menção diretamente na conversa.`)
                .setImage(configBot.bannerEncerrar);

            const menuUsuarios = new ActionRowBuilder().addComponents(
                new UserSelectMenuBuilder()
                    .setCustomId('selecionar_usuario_negocio')
                    .setPlaceholder('Selecione o usuário com quem você está...')
                    .setMaxValues(1)
            );

            const botaoEncerrar = new ActionRowBuilder().addComponents(
                new ButtonBuilder()
                    .setCustomId('encerrar_mediacao')
                    .setLabel('Encerrar Mediação')
                    .setStyle(ButtonStyle.Secondary)
                    .setEmoji('🗑️')
            );

            await canalTicket.send({ 
                embeds: [embedTicket], 
                components: [menuUsuarios, botaoEncerrar] 
            });
        }

        if (interaction.customId === 'encerrar_mediacao') {
            await interaction.reply({ content: 'Finalizando mediação e enviando relatório...', ephemeral: true });

            // Envia o Log no canal configurado para Intermediários Terminados com Sucesso
            if (configBot.canalLogs) {
                const canalDestino = interaction.guild.channels.cache.get(configBot.canalLogs);
                if (canalDestino) {
                    const embedSucesso = new EmbedBuilder()
                        .setColor('#ff0000')
                        .setTitle('🦊 Intermediação Manual')
                        .setThumbnail(configBot.logoSucesso)
                        .addFields(
                            { name: '• Nova Intermediação concluída com sucesso!', value: 'Proof #4095' },
                            { name: '• Valor:', value: 'R$ 8,00', inline: false },
                            { name: '• Participantes:', value: `${interaction.user} e Usuário Convidado`, inline: false },
                            { name: '• Administrador:', value: `${interaction.user}`, inline: false }
                        );

                    await canalDestino.send({ embeds: [embedSucesso] });
                }
            }

            setTimeout(() => interaction.channel.delete().catch(() => null), 5000);
        }
    }

    if (interaction.isUserSelectMenu() && interaction.customId === 'selecionar_usuario_negocio') {
        const usuarioSelecionado = interaction.users.first();
        await interaction.channel.permissionOverwrites.edit(usuarioSelecionado.id, {
            ViewChannel: true,
            SendMessages: true
        });

        await interaction.reply({ content: `🤝 ${usuarioSelecionado} foi adicionado à mediação!`, ephemeral: false });
    }
});

// Registro dos Slash Commands expandido
client.on('messageCreate', async message => {
    if (message.content === '!registrar_comandos' && message.author.id === message.guild.ownerId) {
        const comandos = [
            new SlashCommandBuilder()
                .setName('config')
                .setDescription('Configura a aparência e os canais do sistema de mediação')
                .addStringOption(o => o.setName('banner_abrir').setDescription('Link da imagem do banner inicial'))
                .addStringOption(o => o.setName('banner_encerrar').setDescription('Link da imagem do banner de dentro do ticket'))
                .addStringOption(o => o.setName('logo_sucesso').setDescription('Link da logo que aparece no log de sucesso'))
                .addChannelOption(o => o.setName('canal_painel').setDescription('Canal onde o painel com o botão de abrir vai ficar fixado'))
                .addChannelOption(o => o.setName('categoria_tickets').setDescription('Categoria onde os canais de ticket vão abrir'))
                .addChannelOption(o => o.setName('canal_logs').setDescription('Canal de logs onde caem as mediações terminadas com sucesso')),
            
            new SlashCommandBuilder()
                .setName('painel_mediação')
                .setDescription('Envia o painel de solicitar mediação')
        ];

        await message.guild.commands.set(comandos);
        message.reply('🚀 Comandos Slash atualizados e registrados com sucesso!');
    }
});

client.login(process.env.TOKEN);
