import { CommonModule } from '@angular/common';
import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { StoreService } from '../../shared-services/store.service';
import { SkillCardComponent } from '../skill-card/skill-card.component';
@Component({ selector:'app-skills-view', standalone:true, imports:[CommonModule,FormsModule,SkillCardComponent], templateUrl:'./skills-view.component.html', styleUrl:'./skills-view.component.css' })
export class SkillsViewComponent {
  readonly store=inject(StoreService);
  readonly selected=computed(()=>this.store.skills().find((skill)=>skill.id===this.store.selectedSkillId()) ?? this.store.skills()[0] ?? null);
  readonly id=signal('');
  readonly name=signal('');
  readonly category=signal('custom');
  readonly summary=signal('');
  readonly content=signal('');
  readonly assignTo=signal<string[]>([]);
  select(id:string):void{this.store.selectSkill(id)}
  isSelected(id:string):boolean{return this.selected()?.id===id}
  toggleAgent(agentId:string):void{this.assignTo.update((ids)=>ids.includes(agentId)?ids.filter((id)=>id!==agentId):[...ids,agentId])}
  addSkill():void{const id=this.id().trim(); if(!id)return; this.store.addSkill({id,name:this.name().trim()||undefined,category:this.category().trim()||'custom',summary:this.summary().trim()||undefined,content:this.content().trim()||undefined,assignToAgentIds:this.assignTo()}).subscribe((skill)=>{if(!skill)return; this.id.set(''); this.name.set(''); this.summary.set(''); this.content.set(''); this.assignTo.set([]); this.select(skill.id);});}
}
