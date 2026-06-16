namespace StackLib;

/// <summary>
/// Docker-specific helper methods
/// </summary>
public static class DockerHelpers
{
    /// <summary>
    /// Check if a Docker network exists
    /// </summary>
    public static bool NetworkExists(string name)
    {
        var result = ProcessRunner.Run("docker", $"network ls --filter name=^{name}$ --format {{{{.Name}}}}");
        return result.Success && result.Output.Trim() == name;
    }

    /// <summary>
    /// Create a Docker network if it doesn't exist
    /// </summary>
    public static bool EnsureNetwork(string name, bool verbose = true)
    {
        if (NetworkExists(name))
            return true;

        if (verbose)
            Console.WriteLine($"Creating network: {name}");

        var result = ProcessRunner.Run("docker", $"network create {name}");
        return result.Success;
    }

    /// <summary>
    /// Ensure all networks defined in config exist
    /// </summary>
    public static void EnsureNetworks(StackConfig config)
    {
        foreach (var network in config.Networks.Keys)
        {
            var networkName = $"{config.ProjectName}_{network}";
            EnsureNetwork(networkName);
        }
    }

    /// <summary>
    /// Build docker compose command args with optional override file
    /// </summary>
    public static string BuildComposeArgs(
        string projectName,
        string? overrideFile = null,
        string composeFile = "docker-compose.yml")
    {
        var args = $"compose --project-name {projectName} -f {composeFile}";

        if (!string.IsNullOrEmpty(overrideFile) && File.Exists(overrideFile))
        {
            args += $" -f \"{overrideFile}\"";
        }

        return args;
    }
}
