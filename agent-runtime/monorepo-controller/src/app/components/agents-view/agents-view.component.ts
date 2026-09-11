import { CommonModule } from '@angular/common';
import { Component, computed, inject, signal } from '@angular/core';
import { StoreService } from '../../shared-services/store.service';
import { AgentCardComponent } from '../agent-card/agent-card.component';
import { SkillsViewComponent } from '../skills-view/skills-view.component';
@Component({ selector:'app-agents-view', standalone:true, imports:[CommonModule,AgentCardComponent,SkillsViewComponent], templateUrl:'./agents-view.component.html', styleUrl:'./agents-view.component.css' })
export class AgentsViewComponent { readonly store=inject(StoreService); readonly viewTab=signal('agents'); readonly tab=signal('skills'); readonly agent=computed(()=>this.store.agents().find((item)=>item.id===this.store.selectedAgentId()) ?? this.store.agents()[0] ?? null); select(id:string):void{this.store.selectAgent(id)} isSelected(id:string):boolean{return this.agent()?.id===id} }
