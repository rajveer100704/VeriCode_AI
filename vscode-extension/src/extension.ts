import * as vscode from 'vscode';
import { spawn, ChildProcess } from 'child_process';
import * as path from 'path';

let pythonServerProcess: ChildProcess | undefined;
let requestCounter = 0;
const pendingRequests = new Map<number, { resolve: (val: any) => void, reject: (err: any) => void }>();

export function activate(context: vscode.ExtensionContext) {
    console.log('VeriCode AI Extension Activated');

    // Start Python STDIO Server
    const workspaceFolders = vscode.workspace.workspaceFolders;
    if (workspaceFolders) {
        const rootPath = workspaceFolders[0].uri.fsPath;
        const serverScript = path.join(rootPath, 'src', 'vericode_ai', 'server.py');
        
        pythonServerProcess = spawn('python', [serverScript], { cwd: rootPath });
        
        pythonServerProcess.stdout?.on('data', (data) => {
            const lines = data.toString().split('\n');
            for (const line of lines) {
                if (!line.trim()) continue;
                try {
                    const response = JSON.parse(line);
                    const { id, result, error } = response;
                    if (pendingRequests.has(id)) {
                        const { resolve, reject } = pendingRequests.get(id)!;
                        if (error) reject(error);
                        else resolve(result);
                        pendingRequests.delete(id);
                    }
                } catch (e) {
                    console.error('Failed to parse server response', line);
                }
            }
        });

        pythonServerProcess.stderr?.on('data', (data) => {
            console.log(`[Python Server Log] ${data}`);
        });

        pythonServerProcess.on('exit', (code) => {
            console.error(`Python server exited with code ${code}`);
        });
    }

    // Command: Query VeriCode
    const queryCmd = vscode.commands.registerCommand('vericode-ai.query', async () => {
        const editor = vscode.window.activeTextEditor;
        if (!editor) return;

        const selection = editor.document.getText(editor.selection);
        const codeContext = editor.document.getText();
        
        const userInput = await vscode.window.showInputBox({ prompt: 'Ask VeriCode AI' });
        if (!userInput) return;

        vscode.window.withProgress({
            location: vscode.ProgressLocation.Notification,
            title: "VeriCode AI: Retrieving ground-truth..."
        }, async () => {
            try {
                const result = await sendRpcRequest('query', { 
                    query: userInput, 
                    code: codeContext 
                });
                
                const confidenceStr = (result.confidence * 100).toFixed(1);
                
                // Show Answer
                const doc = await vscode.workspace.openTextDocument({
                    content: `[VeriCode AI Response | Confidence: ${confidenceStr}%]\nSources: ${result.sources.join(', ')}\n\n${result.answer}`,
                    language: 'markdown'
                });
                vscode.window.showTextDocument(doc, vscode.ViewColumn.Beside);
                
            } catch (err) {
                vscode.window.showErrorMessage(`VeriCode check failed: ${JSON.stringify(err)}`);
            }
        });
    });

    // Command: Validate APIs
    const validateCmd = vscode.commands.registerCommand('vericode-ai.validate', async () => {
        const editor = vscode.window.activeTextEditor;
        if (!editor) return;

        const code = editor.document.getText();
        
        vscode.window.withProgress({
            location: vscode.ProgressLocation.Window,
            title: "VeriCode AI: Validating APIs"
        }, async () => {
            try {
                const result = await sendRpcRequest('validate', { code });
                if (result.status === 'error') {
                    // Quick and dirty reporting for Phase 2
                    const errorMsgs = result.errors.map((e: any) => `Line ${e.line}: ${e.message}`).join('\n');
                    vscode.window.showErrorMessage(`VeriCode caught hallucinated APIs:\n${errorMsgs}`, { modal: true });
                } else {
                    vscode.window.showInformationMessage('VeriCode Validator: All APIs map to ground-truth!');
                }
            } catch (err) {
                vscode.window.showErrorMessage(`VeriCode validation failed.`);
            }
        });
    });

    context.subscriptions.push(queryCmd, validateCmd);
}

function sendRpcRequest(method: string, params: any): Promise<any> {
    return new Promise((resolve, reject) => {
        if (!pythonServerProcess || !pythonServerProcess.stdin) {
            return reject('Server not running');
        }
        
        const id = ++requestCounter;
        pendingRequests.set(id, { resolve, reject });
        
        const payload = JSON.stringify({ jsonrpc: "2.0", method, params, id }) + '\n';
        pythonServerProcess.stdin.write(payload);
    });
}

export function deactivate() {
    if (pythonServerProcess) {
        pythonServerProcess.kill();
    }
}
