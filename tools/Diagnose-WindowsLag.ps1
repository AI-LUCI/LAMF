[CmdletBinding()]
param(
    [ValidateRange(5, 600)]
    [int]$DurationSeconds = 30,

    [ValidateRange(1, 10)]
    [int]$IntervalSeconds = 2,

    [string]$OutputDirectory = (Join-Path $env:USERPROFILE 'Desktop\LagDiagnostics')
)

$ErrorActionPreference = 'Stop'

function Get-SafeCimInstance {
    param([string]$ClassName, [string]$Filter, [string]$Namespace = 'root/cimv2')
    try {
        if ($Filter) { return @(Get-CimInstance -Namespace $Namespace -ClassName $ClassName -Filter $Filter -ErrorAction Stop) }
        return @(Get-CimInstance -Namespace $Namespace -ClassName $ClassName -ErrorAction Stop)
    } catch {
        return @()
    }
}

function Get-ProcessSnapshot {
    $snapshot = @{}
    foreach ($process in Get-Process -ErrorAction SilentlyContinue) {
        try {
            $snapshot[$process.Id] = [pscustomobject]@{
                Id = $process.Id
                Name = $process.ProcessName
                CpuSeconds = $process.TotalProcessorTime.TotalSeconds
                IoBytes = $process.IOReadBytes + $process.IOWriteBytes
                WorkingSetBytes = $process.WorkingSet64
            }
        } catch { }
    }
    return $snapshot
}

function Get-Number {
    param($Value)
    if ($null -eq $Value) { return 0.0 }
    return [double]$Value
}

$startedAt = Get-Date
$stamp = $startedAt.ToString('yyyyMMdd-HHmmss')
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$reportPath = Join-Path $OutputDirectory "lag-diagnostic-$stamp.json"

$computer = Get-SafeCimInstance 'Win32_ComputerSystem'
$os = Get-SafeCimInstance 'Win32_OperatingSystem'
$cpu = Get-SafeCimInstance 'Win32_Processor'
$disks = Get-SafeCimInstance 'Win32_LogicalDisk' "DriveType=3"
$physicalDisks = Get-SafeCimInstance 'Win32_DiskDrive'
$video = Get-SafeCimInstance 'Win32_VideoController'
$pageFiles = Get-SafeCimInstance 'Win32_PageFileUsage'
$powerPlan = Get-SafeCimInstance 'Win32_PowerPlan' "IsActive=True" 'root/cimv2/power'

$sampleCount = [Math]::Max(2, [Math]::Ceiling($DurationSeconds / $IntervalSeconds))
$logicalCpuCount = [Math]::Max(1, [int]$computer.NumberOfLogicalProcessors)
$samples = [System.Collections.Generic.List[object]]::new()
$processTotals = @{}
$previousProcesses = Get-ProcessSnapshot

Write-Host "Sampling system responsiveness for approximately $DurationSeconds seconds..." -ForegroundColor Cyan

for ($index = 0; $index -lt $sampleCount; $index++) {
    $sampleStart = Get-Date
    Start-Sleep -Seconds $IntervalSeconds

    $processorPerf = Get-SafeCimInstance 'Win32_PerfFormattedData_PerfOS_Processor' "Name='_Total'"
    $corePerf = @(Get-SafeCimInstance 'Win32_PerfFormattedData_PerfOS_Processor' | Where-Object Name -ne '_Total')
    $memoryPerf = Get-SafeCimInstance 'Win32_PerfFormattedData_PerfOS_Memory'
    $systemPerf = Get-SafeCimInstance 'Win32_PerfFormattedData_PerfOS_System'
    $diskPerf = Get-SafeCimInstance 'Win32_PerfFormattedData_PerfDisk_PhysicalDisk' "Name='_Total'"
    $gpuPerf = Get-SafeCimInstance 'Win32_PerfFormattedData_GPUPerformanceCounters_GPUEngine'
    $currentProcesses = Get-ProcessSnapshot
    $elapsed = [Math]::Max(0.1, ((Get-Date) - $sampleStart).TotalSeconds)

    foreach ($entry in $currentProcesses.GetEnumerator()) {
        $old = $previousProcesses[$entry.Key]
        if ($null -eq $old) { continue }
        $cpuPercent = [Math]::Max(0, (($entry.Value.CpuSeconds - $old.CpuSeconds) / $elapsed / $logicalCpuCount) * 100)
        $ioRate = [Math]::Max(0, ($entry.Value.IoBytes - $old.IoBytes) / $elapsed)
        if (-not $processTotals.ContainsKey($entry.Key)) {
            $processTotals[$entry.Key] = [pscustomobject]@{
                Id = $entry.Key; Name = $entry.Value.Name; CpuPercentSum = 0.0
                IoBytesPerSecondSum = 0.0; PeakWorkingSetBytes = 0L; Samples = 0
            }
        }
        $total = $processTotals[$entry.Key]
        $total.CpuPercentSum += $cpuPercent
        $total.IoBytesPerSecondSum += $ioRate
        $total.PeakWorkingSetBytes = [Math]::Max($total.PeakWorkingSetBytes, $entry.Value.WorkingSetBytes)
        $total.Samples++
    }

    $samples.Add([pscustomobject]@{
        Timestamp = (Get-Date).ToString('o')
        CpuPercent = [Math]::Round((Get-Number $processorPerf.PercentProcessorTime), 2)
        PeakLogicalProcessorPercent = [Math]::Round((Get-Number ($corePerf | Measure-Object PercentProcessorTime -Maximum).Maximum), 2)
        GpuPeakEnginePercent = [Math]::Round((Get-Number ($gpuPerf | Measure-Object UtilizationPercentage -Maximum).Maximum), 2)
        InterruptPercent = [Math]::Round((Get-Number $processorPerf.PercentInterruptTime), 2)
        DpcPercent = [Math]::Round((Get-Number $processorPerf.PercentDPCTime), 2)
        ProcessorQueueLength = [Math]::Round((Get-Number $systemPerf.ProcessorQueueLength), 2)
        AvailableMemoryMB = [Math]::Round((Get-Number $memoryPerf.AvailableMBytes), 2)
        PagesPerSecond = [Math]::Round((Get-Number $memoryPerf.PagesPersec), 2)
        DiskBusyPercent = [Math]::Round((Get-Number $diskPerf.PercentDiskTime), 2)
        DiskQueueLength = [Math]::Round((Get-Number $diskPerf.CurrentDiskQueueLength), 2)
        DiskReadLatencyMs = [Math]::Round((Get-Number $diskPerf.AvgDisksecPerRead) * 1000, 2)
        DiskWriteLatencyMs = [Math]::Round((Get-Number $diskPerf.AvgDisksecPerWrite) * 1000, 2)
    })
    $previousProcesses = $currentProcesses
}

function Get-Average {
    param([string]$Property)
    $values = @($samples | ForEach-Object { [double]$_.$Property })
    if ($values.Count -eq 0) { return 0.0 }
    return [Math]::Round(($values | Measure-Object -Average).Average, 2)
}

function Get-Peak {
    param([string]$Property)
    $values = @($samples | ForEach-Object { [double]$_.$Property })
    if ($values.Count -eq 0) { return 0.0 }
    return [Math]::Round(($values | Measure-Object -Maximum).Maximum, 2)
}

$summary = [ordered]@{
    AverageCpuPercent = Get-Average 'CpuPercent'
    PeakCpuPercent = Get-Peak 'CpuPercent'
    PeakLogicalProcessorPercent = Get-Peak 'PeakLogicalProcessorPercent'
    PeakGpuEnginePercent = Get-Peak 'GpuPeakEnginePercent'
    PeakInterruptPercent = Get-Peak 'InterruptPercent'
    PeakDpcPercent = Get-Peak 'DpcPercent'
    PeakProcessorQueueLength = Get-Peak 'ProcessorQueueLength'
    LowestAvailableMemoryMB = [Math]::Round(($samples | Measure-Object AvailableMemoryMB -Minimum).Minimum, 2)
    PeakPagesPerSecond = Get-Peak 'PagesPerSecond'
    PeakDiskBusyPercent = Get-Peak 'DiskBusyPercent'
    PeakDiskQueueLength = Get-Peak 'DiskQueueLength'
    PeakDiskReadLatencyMs = Get-Peak 'DiskReadLatencyMs'
    PeakDiskWriteLatencyMs = Get-Peak 'DiskWriteLatencyMs'
}

$findings = [System.Collections.Generic.List[string]]::new()
if ($summary.PeakDpcPercent -ge 5 -or $summary.PeakInterruptPercent -ge 10) {
    $findings.Add('High DPC/interrupt activity detected. A device driver, commonly audio, network, storage, USB, or graphics, may be causing stutter.')
}
if ($summary.PeakLogicalProcessorPercent -ge 90 -and $summary.AverageCpuPercent -lt 50) {
    $findings.Add('At least one logical processor was saturated while total CPU remained modest. A single-threaded task can make the PC feel slow without showing high overall CPU.')
}
if ($summary.PeakGpuEnginePercent -ge 90) {
    $findings.Add('A GPU engine reached 90% or higher. Desktop rendering, video decode, or graphics acceleration may be the bottleneck.')
}
if ($summary.PeakDiskReadLatencyMs -ge 30 -or $summary.PeakDiskWriteLatencyMs -ge 30 -or $summary.PeakDiskQueueLength -ge 3) {
    $findings.Add('Storage latency or queueing was high. Overall disk usage can look low while individual requests stall the desktop.')
}
if ($summary.PeakPagesPerSecond -ge 1000 -and $summary.LowestAvailableMemoryMB -lt 2048) {
    $findings.Add('Heavy paging with low available memory was detected.')
}
if ($summary.PeakProcessorQueueLength -gt ($logicalCpuCount * 2) -and $summary.AverageCpuPercent -lt 50) {
    $findings.Add('The processor queue spiked despite modest average CPU use, consistent with short bursts or blocked work.')
}
if ($findings.Count -eq 0) {
    $findings.Add('No clear CPU, memory, storage, paging, or interrupt bottleneck appeared during this sample. Run the tool while the lag is actively happening.')
}

$topProcesses = @($processTotals.Values | ForEach-Object {
    [pscustomobject]@{
        Id = $_.Id
        Name = $_.Name
        AverageCpuPercent = if ($_.Samples) { [Math]::Round($_.CpuPercentSum / $_.Samples, 2) } else { 0 }
        AverageIoMBPerSecond = if ($_.Samples) { [Math]::Round(($_.IoBytesPerSecondSum / $_.Samples) / 1MB, 2) } else { 0 }
        PeakWorkingSetMB = [Math]::Round($_.PeakWorkingSetBytes / 1MB, 1)
    }
} | Sort-Object AverageCpuPercent -Descending | Select-Object -First 15)

$report = [ordered]@{
    ReportVersion = 1
    StartedAt = $startedAt.ToString('o')
    DurationSeconds = $DurationSeconds
    IsAdministrator = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    System = [ordered]@{
        ComputerModel = "$($computer.Manufacturer) $($computer.Model)".Trim()
        Windows = "$($os.Caption) $($os.Version)"
        LastBootTime = $os.LastBootUpTime
        Cpu = ($cpu.Name -join '; ')
        LogicalProcessors = $logicalCpuCount
        InstalledMemoryGB = [Math]::Round((Get-Number $computer.TotalPhysicalMemory) / 1GB, 1)
        ActivePowerPlan = ($powerPlan.ElementName -join '; ')
        VideoControllers = @($video | ForEach-Object { $_.Name })
        Disks = @($physicalDisks | ForEach-Object { [pscustomobject]@{ Model = $_.Model; MediaType = $_.MediaType; Status = $_.Status } })
        Volumes = @($disks | ForEach-Object { [pscustomobject]@{ Drive = $_.DeviceID; FreeGB = [Math]::Round($_.FreeSpace / 1GB, 1); SizeGB = [Math]::Round($_.Size / 1GB, 1) } })
        PageFiles = @($pageFiles | ForEach-Object { [pscustomobject]@{ Name = $_.Name; AllocatedMB = $_.AllocatedBaseSize; CurrentUsageMB = $_.CurrentUsage; PeakUsageMB = $_.PeakUsage } })
    }
    Summary = $summary
    Findings = @($findings)
    TopProcesses = $topProcesses
    Samples = @($samples)
}

$report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $reportPath -Encoding utf8

Write-Host "`nDiagnostic complete" -ForegroundColor Green
Write-Host "Report: $reportPath"
Write-Host "CPU average/peak: $($summary.AverageCpuPercent)% / $($summary.PeakCpuPercent)%"
Write-Host "Peak single logical processor / GPU engine: $($summary.PeakLogicalProcessorPercent)% / $($summary.PeakGpuEnginePercent)%"
Write-Host "Disk latency peak (read/write): $($summary.PeakDiskReadLatencyMs) ms / $($summary.PeakDiskWriteLatencyMs) ms"
Write-Host "DPC/interrupt peak: $($summary.PeakDpcPercent)% / $($summary.PeakInterruptPercent)%"
Write-Host 'Findings:'
$findings | ForEach-Object { Write-Host " - $_" }

[pscustomobject]@{ ReportPath = $reportPath; Summary = $summary; Findings = @($findings) }
