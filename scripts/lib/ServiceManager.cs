namespace StackLib;

/// <summary>
/// Service information for iteration
/// </summary>
public record ServiceInfo(
    string Name,
    string ServiceDir,
    string ComposeFile,
    string? OverrideFile)
{
    public bool ComposeFileExists => File.Exists(ComposeFile);
    public bool HasOverride => !string.IsNullOrEmpty(OverrideFile) && File.Exists(OverrideFile);
    public bool HasDockerfile => File.Exists(Path.Combine(ServiceDir, "Dockerfile"))
        || Directory.EnumerateFiles(ServiceDir, "Dockerfile.*").Any();
}

/// <summary>
/// Manages service iteration and common operations
/// </summary>
public static class ServiceManager
{
    /// <summary>
    /// Get services sorted alphabetically (for start/update)
    /// </summary>
    public static IEnumerable<ServiceInfo> GetServicesAscending(string repoRoot, StackConfig config)
    {
        return GetServices(repoRoot, config, ascending: true);
    }

    /// <summary>
    /// Get services sorted in reverse order (for stop)
    /// </summary>
    public static IEnumerable<ServiceInfo> GetServicesDescending(string repoRoot, StackConfig config)
    {
        return GetServices(repoRoot, config, ascending: false);
    }

    private static IEnumerable<ServiceInfo> GetServices(string repoRoot, StackConfig config, bool ascending)
    {
        var services = ascending
            ? config.Services.OrderBy(s => s)
            : config.Services.OrderByDescending(s => s);

        foreach (var service in services)
        {
            var serviceDir = Path.Combine(repoRoot, "services", service);
            var composeFile = Path.Combine(serviceDir, "docker-compose.yml");
            var overrideFile = Path.Combine(repoRoot, "overrides", $"{service}.override.yml");

            yield return new ServiceInfo(
                service,
                serviceDir,
                composeFile,
                File.Exists(overrideFile) ? overrideFile : null
            );
        }
    }
}
