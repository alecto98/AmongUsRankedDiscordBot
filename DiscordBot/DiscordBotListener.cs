using Impostor.Api.Events;
using Impostor.Api.Events.Client;
using Impostor.Api.Events.Managers;
using Impostor.Api.Events.Meeting;
using Impostor.Api.Events.Player;
using Impostor.Api.Games;
using Impostor.Api.Innersloth;
using Impostor.Api.Net;
using Impostor.Api.Net.Custom;
using Impostor.Api.Net.Inner;
using Impostor.Api.Net.Inner.Objects;
using Impostor.Api.Net.Inner.Objects.ShipStatus;
using Impostor.Api.Net.Messages.Rpcs;
using Microsoft.Extensions.Logging;
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using RabbitMQ.Client;
using System.Net.Sockets;

namespace DiscordBot
{
    public class DiscordBotListener : IEventListener
    {
        
        private readonly ILogger<DiscordBot> _logger;
        private readonly string hostName = "localhost";
        private IEventManager _eventManager;

        public DiscordBotListener(ILogger<DiscordBot> logger, IEventManager eventManager)
        {   
            _logger = logger;
            _eventManager = eventManager;
        }

        [EventListener]
        public void OnGameStarted(IGameStartedEvent e)
        {
            _logger.LogInformation($"Game is starting.");
            string pattern = "*_match.json";
            string workingDirectory = Environment.CurrentDirectory;
            string directoryPath = Path.Combine(workingDirectory, "plugins", "MatchLog");
            string[] matchFiles = Directory.GetFiles(directoryPath, pattern);
            var eventData = new
            {
                EventName = "GameStart",
                MatchID = matchFiles.Length - 1,
                GameCode = e.Game.Code,
                Players = e.Game.Players.Select(p => p.Character.PlayerInfo.PlayerName).ToList(),
                PlayerColors = e.Game.Players.Select(p => p.Character.PlayerInfo.CurrentOutfit.Color).ToList(),
                Impostors = e.Game.Players.Where(p => p.Character.PlayerInfo.IsImpostor).Select(p => p.Character.PlayerInfo.PlayerName).ToList(),
                Crewmates = e.Game.Players.Where(p => !p.Character.PlayerInfo.IsImpostor).Select(p => p.Character.PlayerInfo.PlayerName).ToList()
            };
            string jsonData = JsonSerializer.Serialize(eventData);
            _logger.LogInformation(jsonData);
            SendMessage(jsonData);
        }


        [EventListener]
        public void onMeetingStart(IMeetingStartedEvent e)
        {
            _logger.LogInformation($"Meeting Started.");

            var eventData = new
            {
                EventName = "MeetingStart",
                GameCode = e.Game.Code,
                Players = e.Game.Players.Select(p => p.Character.PlayerInfo.PlayerName).ToList(),
                DeadPlayers = e.Game.Players.Where(p => p.Character.PlayerInfo.IsDead).Select(p => p.Character.PlayerInfo.PlayerName).ToList()
            };
            string jsonData = JsonSerializer.Serialize(eventData);
            _logger.LogInformation(jsonData);
            SendMessage(jsonData);
        }

        [EventListener]
        public void onMeetingEnd(IMeetingEndedEvent e)
        {
            _logger.LogInformation($"Meeting Ended.");
            var eventData = new
            {
                EventName = "MeetingEnd",
                GameCode = e.Game.Code,
                Players = e.Game.Players.Select(p => p.Character.PlayerInfo.PlayerName).ToList(),
                DeadPlayers = e.Game.Players.Where(p => p.Character.PlayerInfo.IsDead).Select(p => p.Character.PlayerInfo.PlayerName).ToList()
            };
            string jsonData = JsonSerializer.Serialize(eventData);
            _logger.LogInformation(jsonData);
            SendMessage(jsonData);
        }

        [EventListener(EventPriority.Lowest)]
        public void OnGameEnded(IGameEndedEvent e)
        {
            _logger.LogInformation($"Game has ended.");
            string pattern = "*_match.json";
            string workingDirectory = Environment.CurrentDirectory;
            string directoryPath = Path.Combine(workingDirectory, "plugins", "MatchLog");
            string[] matchFiles = Directory.GetFiles(directoryPath, pattern);

            var eventData = new
            {
                EventName = "GameEnd",
                MatchID = matchFiles.Length - 2,
                GameCode = e.Game.Code,
                Players = e.Game.Players.Select(p => p.Character.PlayerInfo.PlayerName).ToList(),
                PlayerColors = e.Game.Players.Select(p => p.Character.PlayerInfo.CurrentOutfit.Color).ToList(),
                DeadPlayers = e.Game.Players.Where(p => p.Character.PlayerInfo.IsDead).Select(p => p.Character.PlayerInfo.PlayerName).ToList(),
                Impostors = e.Game.Players.Where(p => p.Character.PlayerInfo.IsImpostor).Select(p => p.Character.PlayerInfo.PlayerName).ToList(),
                Crewmates = e.Game.Players.Where(p => !p.Character.PlayerInfo.IsImpostor).Select(p => p.Character.PlayerInfo.PlayerName).ToList(),
                Result = e.GameOverReason
            };
            string jsonData = JsonSerializer.Serialize(eventData);
            _logger.LogInformation(jsonData);
            SendMessage(jsonData);
        }
        private void SendMessage(string message)
        {
            _logger.LogDebug(message);
                
            try
            {
                // Connect to the server
                using (var client = new TcpClient(hostName, 5000))
                {
                    // Get the network stream
                    using (var stream = client.GetStream())
                    {
                        // Convert the message to bytes
                        byte[] data = Encoding.UTF8.GetBytes(message);

                        // Send the message
                        stream.Write(data, 0, data.Length);

                        _logger.LogInformation($"Message sent: {message}");
                    }
                }
            }
            catch (Exception ex)
            {
                _logger.LogError($"An error occurred while sending message: {ex.Message}");
            }
        }
    }
}


//}
