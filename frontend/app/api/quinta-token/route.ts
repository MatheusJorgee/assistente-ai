// Entrega o token de sessão do backend ao navegador (o arquivo só existe no servidor do Next, nunca
// vai para o bundle público). Só responde a quem chega por localhost e não é uma página de outro site.
import { readFile } from 'node:fs/promises'
import path from 'node:path'
import { NextResponse } from 'next/server'
import { hostPermitido, origemPermitida } from '@/lib/tokenRota'

export const dynamic = 'force-dynamic'

export async function GET(req: Request) {
  const h = req.headers
  if (!hostPermitido(h.get('host')) || !origemPermitida(h.get('sec-fetch-site'), h.get('origin'), h.get('host'))) {
    return NextResponse.json({ token: null }, { status: 403, headers: { 'Cache-Control': 'no-store' } })
  }
  const arquivo = process.env.QUINTA_TOKEN_FILE || path.resolve(process.cwd(), '..', 'backend', '.runtime', 'session_token')
  try {
    const token = (await readFile(arquivo, 'utf-8')).trim()
    return NextResponse.json({ token: token || null }, { headers: { 'Cache-Control': 'no-store' } })
  } catch {
    // backend ainda não subiu (ou modo off): o cliente segue sem token; o backend decide se aceita
    return NextResponse.json({ token: null }, { headers: { 'Cache-Control': 'no-store' } })
  }
}
