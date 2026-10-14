$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;

public static class DeMarkNativeMethods {
    [DllImport("user32.dll", SetLastError = true)]
    public static extern bool DestroyIcon(IntPtr hIcon);
}
"@

$assetDir = Join-Path $PSScriptRoot "installer_assets"
New-Item -ItemType Directory -Force -Path $assetDir | Out-Null

function New-RoundedRectanglePath {
    param(
        [float]$X,
        [float]$Y,
        [float]$Width,
        [float]$Height,
        [float]$Radius
    )

    $path = New-Object System.Drawing.Drawing2D.GraphicsPath
    $diameter = $Radius * 2
    $path.AddArc($X, $Y, $diameter, $diameter, 180, 90)
    $path.AddArc($X + $Width - $diameter, $Y, $diameter, $diameter, 270, 90)
    $path.AddArc($X + $Width - $diameter, $Y + $Height - $diameter, $diameter, $diameter, 0, 90)
    $path.AddArc($X, $Y + $Height - $diameter, $diameter, $diameter, 90, 90)
    $path.CloseFigure()
    return $path
}

function Save-BitmapAsIco {
    param(
        [System.Drawing.Bitmap]$Bitmap,
        [string]$IcoPath
    )

    $iconSize = 64
    $resizedBitmap = [System.Drawing.Bitmap]::new($iconSize, $iconSize)
    $graphics = [System.Drawing.Graphics]::FromImage($resizedBitmap)
    $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $graphics.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
    $graphics.Clear([System.Drawing.Color]::Transparent)
    $graphics.DrawImage($Bitmap, 0, 0, $iconSize, $iconSize)

    $iconHandle = $resizedBitmap.GetHicon()
    try {
        $icon = [System.Drawing.Icon]::FromHandle($iconHandle)
        $stream = [System.IO.File]::Open($IcoPath, [System.IO.FileMode]::Create)
        try {
            $icon.Save($stream)
        }
        finally {
            $stream.Dispose()
            $icon.Dispose()
        }
    }
    finally {
        $graphics.Dispose()
        $resizedBitmap.Dispose()
        [DeMarkNativeMethods]::DestroyIcon($iconHandle) | Out-Null
    }
}

function New-LinePen {
    param(
        [System.Drawing.Color]$Color,
        [float]$Width
    )

    $pen = New-Object System.Drawing.Pen($Color, $Width)
    $pen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
    $pen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
    return $pen
}

$iconBitmap = [System.Drawing.Bitmap]::new(256, 256)
$graphics = [System.Drawing.Graphics]::FromImage($iconBitmap)
$graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
$graphics.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit
$graphics.Clear([System.Drawing.Color]::Transparent)

$shellPath = New-RoundedRectanglePath -X 18 -Y 18 -Width 220 -Height 220 -Radius 48
$shellBrush = [System.Drawing.Drawing2D.LinearGradientBrush]::new(
    [System.Drawing.Rectangle]::new(18, 18, 220, 220),
    [System.Drawing.Color]::FromArgb(255, 17, 57, 89),
    [System.Drawing.Color]::FromArgb(255, 37, 143, 133),
    45
)
$shellPen = [System.Drawing.Pen]::new([System.Drawing.Color]::FromArgb(70, 255, 255, 255), 3)
$accentBrush = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::FromArgb(255, 255, 183, 77))
$cardFill = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::FromArgb(34, 255, 255, 255))
$cardPen = [System.Drawing.Pen]::new([System.Drawing.Color]::FromArgb(230, 255, 255, 255), 6)
$artPen = [System.Drawing.Pen]::new([System.Drawing.Color]::FromArgb(210, 255, 183, 77), 5)
$arrowPen = New-LinePen -Color ([System.Drawing.Color]::FromArgb(240, 255, 255, 255)) -Width 12
$cardBack = New-RoundedRectanglePath -X 84 -Y 62 -Width 104 -Height 78 -Radius 16
$cardFront = New-RoundedRectanglePath -X 54 -Y 86 -Width 128 -Height 96 -Radius 18

$graphics.FillPath($shellBrush, $shellPath)
$graphics.DrawPath($shellPen, $shellPath)
$graphics.FillEllipse($accentBrush, 178, 34, 34, 34)
$graphics.FillPath($cardFill, $cardBack)
$graphics.DrawPath($cardPen, $cardBack)
$graphics.FillPath($cardFill, $cardFront)
$graphics.DrawPath($cardPen, $cardFront)
$graphics.DrawLine($artPen, 70, 158, 101, 126)
$graphics.DrawLine($artPen, 101, 126, 124, 149)
$graphics.DrawLine($artPen, 124, 149, 153, 119)
$graphics.DrawLine($artPen, 78, 162, 158, 162)
$graphics.DrawLine($arrowPen, 128, 174, 128, 208)
$graphics.DrawLine($arrowPen, 110, 192, 128, 210)
$graphics.DrawLine($arrowPen, 146, 192, 128, 210)
$graphics.DrawLine($arrowPen, 96, 222, 160, 222)

Save-BitmapAsIco -Bitmap $iconBitmap -IcoPath (Join-Path $assetDir "DeMarkApp.ico")

$arrowPen.Dispose()
$artPen.Dispose()
$cardPen.Dispose()
$cardFill.Dispose()
$accentBrush.Dispose()
$shellPen.Dispose()
$shellBrush.Dispose()
$cardBack.Dispose()
$cardFront.Dispose()
$shellPath.Dispose()
$graphics.Dispose()
$iconBitmap.Dispose()

$wizardBitmap = [System.Drawing.Bitmap]::new(164, 314)
$graphics = [System.Drawing.Graphics]::FromImage($wizardBitmap)
$graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
$graphics.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit

$backgroundBrush = [System.Drawing.Drawing2D.LinearGradientBrush]::new(
    [System.Drawing.Rectangle]::new(0, 0, 164, 314),
    [System.Drawing.Color]::FromArgb(255, 14, 38, 66),
    [System.Drawing.Color]::FromArgb(255, 29, 115, 122),
    90
)
$glowBrush = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::FromArgb(28, 255, 255, 255))
$accentBrush = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::FromArgb(255, 255, 183, 77))
$cardFill = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::FromArgb(28, 255, 255, 255))
$cardPen = [System.Drawing.Pen]::new([System.Drawing.Color]::FromArgb(235, 255, 255, 255), 4)
$artPen = [System.Drawing.Pen]::new([System.Drawing.Color]::FromArgb(220, 255, 183, 77), 4)
$arrowPen = New-LinePen -Color ([System.Drawing.Color]::FromArgb(240, 255, 255, 255)) -Width 8
$titleFont = [System.Drawing.Font]::new("Microsoft YaHei UI", 23, [System.Drawing.FontStyle]::Bold)
$subtitleFont = [System.Drawing.Font]::new("Microsoft YaHei UI", 11, [System.Drawing.FontStyle]::Bold)
$bodyFont = [System.Drawing.Font]::new("Microsoft YaHei UI", 8.5, [System.Drawing.FontStyle]::Regular)
$softBrush = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::FromArgb(220, 234, 244, 255))
$mutedBrush = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::FromArgb(200, 214, 229, 240))
$stringFormat = New-Object System.Drawing.StringFormat
$stringFormat.Alignment = [System.Drawing.StringAlignment]::Near
$stringFormat.LineAlignment = [System.Drawing.StringAlignment]::Near
$bannerCardBack = New-RoundedRectanglePath -X 31 -Y 52 -Width 92 -Height 70 -Radius 14
$bannerCardFront = New-RoundedRectanglePath -X 48 -Y 72 -Width 92 -Height 70 -Radius 14

$graphics.FillRectangle($backgroundBrush, 0, 0, 164, 314)
$graphics.FillEllipse($glowBrush, -30, 190, 140, 140)
$graphics.FillEllipse($glowBrush, 94, -20, 90, 90)
$graphics.FillEllipse($accentBrush, 112, 22, 24, 24)
$graphics.FillPath($cardFill, $bannerCardBack)
$graphics.DrawPath($cardPen, $bannerCardBack)
$graphics.FillPath($cardFill, $bannerCardFront)
$graphics.DrawPath($cardPen, $bannerCardFront)
$graphics.DrawLine($artPen, 60, 127, 80, 103)
$graphics.DrawLine($artPen, 80, 103, 98, 120)
$graphics.DrawLine($artPen, 98, 120, 118, 96)
$graphics.DrawLine($artPen, 64, 130, 118, 130)
$graphics.DrawLine($arrowPen, 82, 145, 82, 172)
$graphics.DrawLine($arrowPen, 69, 160, 82, 173)
$graphics.DrawLine($arrowPen, 95, 160, 82, 173)
$graphics.DrawLine($arrowPen, 54, 184, 110, 184)
$graphics.DrawString("DeMark", $titleFont, [System.Drawing.Brushes]::White, [System.Drawing.RectangleF]::new(18, 203, 128, 34), $stringFormat)
$graphics.DrawString("Guided Setup", $subtitleFont, $softBrush, [System.Drawing.RectangleF]::new(20, 238, 120, 24), $stringFormat)
$graphics.DrawString("Multi-platform image extractor", $bodyFont, $mutedBrush, [System.Drawing.RectangleF]::new(20, 259, 126, 18), $stringFormat)
$graphics.DrawString("818ps / Canva / Chuangkit", $bodyFont, $mutedBrush, [System.Drawing.RectangleF]::new(20, 278, 126, 24), $stringFormat)
$wizardBitmap.Save((Join-Path $assetDir "DeMarkWizardImage.bmp"), [System.Drawing.Imaging.ImageFormat]::Bmp)

$bannerCardFront.Dispose()
$bannerCardBack.Dispose()
$stringFormat.Dispose()
$mutedBrush.Dispose()
$softBrush.Dispose()
$bodyFont.Dispose()
$subtitleFont.Dispose()
$titleFont.Dispose()
$arrowPen.Dispose()
$artPen.Dispose()
$cardPen.Dispose()
$cardFill.Dispose()
$accentBrush.Dispose()
$glowBrush.Dispose()
$backgroundBrush.Dispose()
$graphics.Dispose()
$wizardBitmap.Dispose()

$smallBitmap = [System.Drawing.Bitmap]::new(55, 55)
$graphics = [System.Drawing.Graphics]::FromImage($smallBitmap)
$graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
$graphics.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit

$smallBackgroundBrush = [System.Drawing.Drawing2D.LinearGradientBrush]::new(
    [System.Drawing.Rectangle]::new(0, 0, 55, 55),
    [System.Drawing.Color]::FromArgb(255, 20, 68, 103),
    [System.Drawing.Color]::FromArgb(255, 38, 145, 136),
    45
)
$smallAccentBrush = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::FromArgb(255, 255, 183, 77))
$smallFill = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::FromArgb(30, 255, 255, 255))
$smallOutline = [System.Drawing.Pen]::new([System.Drawing.Color]::FromArgb(230, 255, 255, 255), 2)
$smallArtPen = [System.Drawing.Pen]::new([System.Drawing.Color]::FromArgb(225, 255, 183, 77), 2)
$smallArrowPen = New-LinePen -Color ([System.Drawing.Color]::FromArgb(245, 255, 255, 255)) -Width 4
$smallBasePen = New-LinePen -Color ([System.Drawing.Color]::FromArgb(245, 255, 255, 255)) -Width 3
$smallCard = New-RoundedRectanglePath -X 6 -Y 7 -Width 28 -Height 21 -Radius 5

$graphics.FillRectangle($smallBackgroundBrush, 0, 0, 55, 55)
$graphics.FillPath($smallFill, $smallCard)
$graphics.DrawPath($smallOutline, $smallCard)
$graphics.DrawLine($smallArtPen, 12, 23, 20, 15)
$graphics.DrawLine($smallArtPen, 20, 15, 26, 21)
$graphics.DrawLine($smallArrowPen, 28, 30, 28, 42)
$graphics.DrawLine($smallArrowPen, 21, 36, 28, 43)
$graphics.DrawLine($smallArrowPen, 35, 36, 28, 43)
$graphics.DrawLine($smallBasePen, 16, 47, 40, 47)
$graphics.FillEllipse($smallAccentBrush, 38, 8, 9, 9)
$smallBitmap.Save((Join-Path $assetDir "DeMarkWizardSmallImage.bmp"), [System.Drawing.Imaging.ImageFormat]::Bmp)

$smallCard.Dispose()
$smallBasePen.Dispose()
$smallArrowPen.Dispose()
$smallArtPen.Dispose()
$smallOutline.Dispose()
$smallFill.Dispose()
$smallAccentBrush.Dispose()
$smallBackgroundBrush.Dispose()
$graphics.Dispose()
$smallBitmap.Dispose()
