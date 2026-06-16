import fs from 'node:fs';
import path from 'node:path';

const cwd = process.cwd();
const logsDir = path.join(cwd, 'logs');
const versionsDir = path.join(logsDir, 'versions');
const templatePath = path.join(logsDir, 'TEMPLATE.md');

function parseArgs(rawArgs) {
    const args = [...rawArgs];
    const options = {
        dryRun: false,
        force: false,
        version: null,
        authors: ['dev'],
    };

    while (args.length > 0) {
        const value = args.shift();
        if (!value) continue;

        if (value === '--dry-run') {
            options.dryRun = true;
            continue;
        }
        if (value === '--force') {
            options.force = true;
            continue;
        }
        if (value.startsWith('--authors=')) {
            const authorsRaw = value.split('=', 2)[1] ?? '';
            const authors = authorsRaw
                .split(',')
                .map(author => author.trim())
                .filter(Boolean);
            if (authors.length > 0) {
                options.authors = authors;
            }
            continue;
        }
        if (!options.version) {
            options.version = value.trim();
        }
    }

    return options;
}

function parseSemver(version) {
    const match = /^(\d+)\.(\d+)\.(\d+)$/.exec(version);
    if (!match) return null;
    return {
        major: Number(match[1]),
        minor: Number(match[2]),
        patch: Number(match[3]),
    };
}

function compareSemver(a, b) {
    if (a.major !== b.major) return a.major - b.major;
    if (a.minor !== b.minor) return a.minor - b.minor;
    return a.patch - b.patch;
}

function toSemverString(version) {
    return `${version.major}.${version.minor}.${version.patch}`;
}

function findLatestVersion() {
    if (!fs.existsSync(versionsDir)) return null;
    const files = fs.readdirSync(versionsDir, { withFileTypes: true })
        .filter(item => item.isFile() && item.name.endsWith('.md'))
        .map(item => item.name.replace(/\.md$/i, ''))
        .map(name => ({ name, semver: parseSemver(name) }))
        .filter(item => item.semver !== null);

    if (files.length === 0) return null;
    files.sort((left, right) => compareSemver(left.semver, right.semver));
    return files[files.length - 1].name;
}

function nextPatchVersion(previousVersion) {
    if (!previousVersion) {
        return '1.0.0';
    }
    const parsed = parseSemver(previousVersion);
    if (!parsed) {
        throw new Error(`Versao invalida encontrada no historico: ${previousVersion}`);
    }
    parsed.patch += 1;
    return toSemverString(parsed);
}

function formatDateParts(now) {
    const year = now.getFullYear();
    const month = String(now.getMonth() + 1).padStart(2, '0');
    const day = String(now.getDate()).padStart(2, '0');
    const hours = String(now.getHours()).padStart(2, '0');
    const minutes = String(now.getMinutes()).padStart(2, '0');
    const offsetMinutes = -now.getTimezoneOffset();
    const signal = offsetMinutes >= 0 ? '+' : '-';
    const offsetAbsolute = Math.abs(offsetMinutes);
    const offsetHours = String(Math.floor(offsetAbsolute / 60)).padStart(2, '0');
    const offsetMins = String(offsetAbsolute % 60).padStart(2, '0');
    const timezone = `${signal}${offsetHours}:${offsetMins}`;

    return {
        date: `${year}-${month}-${day}`,
        time: `${hours}:${minutes} ${timezone}`,
    };
}

function buildFromTemplate(templateContent, version, baseVersion, authors, dateParts) {
    const authorLines = authors.map(author => `  - ${author}`).join('\n');
    let content = templateContent;
    content = content.replaceAll('`x.y.z`', `\`${version}\``);
    content = content.replace(/^version:\s*x\.y\.z$/m, `version: ${version}`);
    content = content.replace(/^date:\s*YYYY-MM-DD$/m, `date: ${dateParts.date}`);
    content = content.replace(/^time:\s*"HH:MM TZ"$/m, `time: "${dateParts.time}"`);
    content = content.replace(/^base_app_version:\s*x\.y\.z$/m, `base_app_version: ${baseVersion}`);
    content = content.replace(/authors:\n(?:\s*-\s.*\n)+/m, `authors:\n${authorLines}\n`);

    if (!/^base_app_version:/m.test(content)) {
        content = content.replace(/^status:\s*done$/m, `status: done\nbase_app_version: ${baseVersion}`);
    }

    return content;
}

function ensureFolder(folderPath) {
    if (!fs.existsSync(folderPath)) {
        fs.mkdirSync(folderPath, { recursive: true });
    }
}

function run() {
    const options = parseArgs(process.argv.slice(2));
    ensureFolder(logsDir);
    ensureFolder(versionsDir);

    if (!fs.existsSync(templatePath)) {
        throw new Error(`Template nao encontrado: ${templatePath}`);
    }

    const latestVersion = findLatestVersion();
    const version = options.version || nextPatchVersion(latestVersion);
    const parsedInput = parseSemver(version);
    if (!parsedInput) {
        throw new Error(`Versao invalida: ${version}. Use formato x.y.z`);
    }

    const outputPath = path.join(versionsDir, `${version}.md`);
    if (fs.existsSync(outputPath) && !options.force) {
        throw new Error(`Arquivo ja existe: ${outputPath}. Use --force para sobrescrever.`);
    }

    const templateContent = fs.readFileSync(templatePath, 'utf8');
    const now = new Date();
    const dateParts = formatDateParts(now);
    const baseVersion = latestVersion || version;
    const content = buildFromTemplate(templateContent, version, baseVersion, options.authors, dateParts);

    if (options.dryRun) {
        console.log(`[dry-run] Arquivo alvo: ${outputPath}`);
        console.log('---');
        console.log(content);
        return;
    }

    fs.writeFileSync(outputPath, content, 'utf8');
    console.log(`Log criado: ${outputPath}`);
}

try {
    run();
} catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    console.error(`Erro: ${message}`);
    process.exitCode = 1;
}
