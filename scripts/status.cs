#!/usr/bin/env -S dotnet run
#:project lib/StackLib.csproj

using StackLib;

var repoRoot = Environment.CurrentDirectory;
var config = ConfigLoader.LoadConfig(repoRoot);

Console.WriteLine($"Project: {config.ProjectName}");
Console.WriteLine();

var result = ProcessRunner.Run("docker",
    $"ps --filter name={config.ProjectName} --format \"table {{{{.Names}}}}\\t{{{{.Status}}}}\\t{{{{.Ports}}}}\"");

if (result.Success)
{
    Console.WriteLine(result.Output);
}
else
{
    Console.WriteLine("Failed to get container status");
}
