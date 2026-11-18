import React,{useEffect,useRef,useState} from 'react';
import {Play,Pause,X} from '@phosphor-icons/react';
import {time} from './api';
export function Wave({peaks=[],progress=0}) {
 const ref=useRef();useEffect(()=>{const c=ref.current;function draw(){const {width:w,height:h}=c.getBoundingClientRect(),d=devicePixelRatio||1;c.width=w*d;c.height=h*d;const ctx=c.getContext('2d');ctx.scale(d,d);if(!peaks.length){ctx.fillStyle='#d5e0da';ctx.fillRect(0,h/2,w,1);return;}peaks.forEach((p,i)=>{const v=Math.max(2,p*(h-4));ctx.fillStyle=i/peaks.length<=progress?'#006d60':'#94b5ad';ctx.fillRect(i*w/peaks.length,(h-v)/2,Math.max(1,w/peaks.length-2),v);});}draw();const o=new ResizeObserver(draw);o.observe(c);return()=>o.disconnect();},[peaks,progress]);
 return <canvas className="wave" ref={ref} aria-label="音频波形"/>;
}
export function Player({src,peaks,duration=0,notify}) {
 const ref=useRef(),[playing,setPlaying]=useState(false),[position,setPosition]=useState(0);
 useEffect(()=>{setPlaying(false);setPosition(0);},[src]);
 return <div className="audio-player"><audio ref={ref} src={src} preload="metadata" onPlay={()=>setPlaying(true)} onPause={()=>setPlaying(false)} onEnded={()=>setPlaying(false)} onTimeUpdate={e=>setPosition(e.currentTarget.currentTime)} onError={()=>notify?.('音频无法播放，请下载检查格式。')}/><button className="play-round" aria-label={playing?'暂停':'播放'} onClick={()=>playing?ref.current.pause():ref.current.play().catch(()=>notify?.('浏览器未能播放音频。'))}>{playing?<Pause weight="fill"/>:<Play weight="fill"/>}</button><div className="wave-seek" role="slider" aria-label="播放进度" aria-valuemin={0} aria-valuemax={duration} aria-valuenow={Math.floor(position)} tabIndex={0} onKeyDown={e=>{if(['ArrowLeft','ArrowRight'].includes(e.key))ref.current.currentTime=Math.max(0,Math.min(duration,position+(e.key==='ArrowRight'?2:-2)));}} onClick={e=>{const r=e.currentTarget.getBoundingClientRect();ref.current.currentTime=(e.clientX-r.left)/r.width*duration;}}><Wave peaks={peaks} progress={position/(duration||1)}/></div><span className="time">{time(position)} / {time(duration)}</span></div>;
}
export function Modal({title,close,children}) {
 const ref=useRef();useEffect(()=>{const d=ref.current;d.showModal();return()=>{if(d.open)d.close();};},[]);
 return <dialog ref={ref} onCancel={close} onClick={e=>{if(e.target===e.currentTarget)close();}}><div className="modal-head"><h2>{title}</h2><button className="icon-button" aria-label="关闭" onClick={close}><X/></button></div>{children}</dialog>;
}
