using Impostor.Api.Events.Managers;
using Impostor.Api.Plugins;
using Microsoft.Extensions.Logging;
using System;

namespace DiscordBot
{
    /// <summary>
    ///     The metadata information of your plugin, this is required.
    /// </summary>
    [ImpostorPlugin(
        id: "dixter.auc.discordbot",
        name: "DiscordBot",
        author: "Aiden",
        version: "1.0.0")]
    [Obsolete]
    public class DiscordBot : PluginBase // This is also required ": PluginBase".
    {
        /// <summary>
        ///     A logger that works seamlessly with the server.
        /// </summary>
        private readonly ILogger<DiscordBot> _logger;
        public readonly IEventManager _eventManager;
        private IDisposable _unregister;

        /// <summary>
        ///     The constructor of the plugin. There are a few parameters you can add here and they
        ///     will be injected automatically by the server, two examples are used here.
        ///
        ///     They are not necessary but very recommended.
        /// </summary>
        /// <param name="logger">
        ///     A logger to write messages in the console.
        /// </param>
        /// <param name="eventManager">
        ///     An event manager to register event listeners.
        ///     Useful if you want your plugin to interact with the game.
        /// </param>
        public DiscordBot(ILogger<DiscordBot> logger, IEventManager eventManager)
        {
            _logger = logger;
            _eventManager = eventManager;
        }

        /// <summary>
        ///     This is called when your plugin is enabled by the server.
        /// </summary>
        /// <returns></returns>
        public override ValueTask EnableAsync()
        {
            _logger.LogInformation("Discord Bot connection is being enabled.");
            _unregister = _eventManager.RegisterListener(new DiscordBotListener(_logger, _eventManager));
            return default;
        }

        /// <summary>
        ///     This is called when your plugin is disabled by the server.
        ///     Most likely because it is shutting down, this is the place to clean up any managed resources.
        /// </summary>
        /// <returns></returns>
        public override ValueTask DisableAsync()
        {
            _logger.LogInformation("Discord Bot connection is being disabled.");
            return default;
        }
    }
}
