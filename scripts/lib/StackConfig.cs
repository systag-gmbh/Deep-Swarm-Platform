using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace StackLib;

/// <summary>
/// Represents the stack configuration loaded from stack.json
/// </summary>
public class StackConfig
{
    public string ProjectName { get; init; } = "stack";
    public string DataPath { get; init; } = "/docker/data";
    public string BackupPath { get; init; } = "/docker";
    public string BackupOutputPath { get; init; } = "/backups";
    public Dictionary<string, object> Networks { get; init; } = new();
    public List<string> Services { get; init; } = new();
    public JObject RawConfig { get; init; } = new();
}

/// <summary>
/// Loads and merges stack configuration files
/// </summary>
public static class ConfigLoader
{
    /// <summary>
    /// Load config from stack.json, merged with stack.local.json if present
    /// </summary>
    public static StackConfig LoadConfig(string repoRoot)
    {
        var config = LoadRawConfig(repoRoot);

        return new StackConfig
        {
            ProjectName = config["project_name"]?.ToString() ?? "stack",
            DataPath = config["data_path"]?.ToString() ?? "/docker/data",
            BackupPath = config["backup_path"]?.ToString() ?? "/docker",
            BackupOutputPath = config["backup_output_path"]?.ToString() ?? "/backups",
            Networks = config["networks"]?.ToObject<Dictionary<string, object>>() ?? new(),
            Services = config["services"]?.ToObject<List<string>>() ?? new(),
            RawConfig = config
        };
    }

    /// <summary>
    /// Load raw JObject config (for advanced use cases)
    /// </summary>
    public static JObject LoadRawConfig(string repoRoot)
    {
        var baseConfigPath = Path.Combine(repoRoot, "stack.json");
        var localConfigPath = Path.Combine(repoRoot, "stack.local.json");

        JObject config = new JObject();

        if (File.Exists(baseConfigPath))
        {
            var baseContent = File.ReadAllText(baseConfigPath);
            config = JObject.Parse(baseContent);
        }

        if (File.Exists(localConfigPath))
        {
            var localContent = File.ReadAllText(localConfigPath);
            var localConfig = JObject.Parse(localContent);

            config.Merge(localConfig, new JsonMergeSettings
            {
                MergeArrayHandling = MergeArrayHandling.Replace
            });
        }

        return config;
    }

    /// <summary>
    /// Load environment variables from .env file
    /// </summary>
    public static Dictionary<string, string> LoadEnvFile(string path)
    {
        var envVars = new Dictionary<string, string>();

        if (!File.Exists(path))
            return envVars;

        foreach (var line in File.ReadAllLines(path))
        {
            var trimmed = line.Trim();
            if (string.IsNullOrEmpty(trimmed) || trimmed.StartsWith("#"))
                continue;

            var eqIndex = trimmed.IndexOf('=');
            if (eqIndex > 0)
            {
                var key = trimmed.Substring(0, eqIndex).Trim();
                var value = trimmed.Substring(eqIndex + 1).Trim();
                envVars[key] = value;
            }
        }

        return envVars;
    }

    /// <summary>
    /// Build environment dictionary with config values
    /// </summary>
    public static Dictionary<string, string> BuildEnvironment(string repoRoot, StackConfig config)
    {
        var envVars = LoadEnvFile(Path.Combine(repoRoot, ".env"));
        envVars["PROJECT_NAME"] = config.ProjectName;
        envVars["DATA_PATH"] = config.DataPath;
        envVars["BACKUP_PATH"] = config.BackupPath;
        envVars["BACKUP_OUTPUT_PATH"] = config.BackupOutputPath;
        return envVars;
    }
}
