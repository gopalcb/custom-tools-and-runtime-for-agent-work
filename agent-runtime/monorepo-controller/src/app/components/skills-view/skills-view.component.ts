import { CommonModule } from '@angular/common';
import { Component, computed, inject } from '@angular/core';
import { StoreService } from '../../shared-services/store.service';
import { SkillCardComponent } from '../skill-card/skill-card.component';
@Component({ selector:'app-skills-view', standalone:true, imports:[CommonModule,SkillCardComponent], templateUrl:'./skills-view.component.html', styleUrl:'./skills-view.component.css' })
export class SkillsViewComponent { readonly store=inject(StoreService); readonly selected=computed(()=>this.store.skills().find((skill)=>skill.id===this.store.selectedSkillId()) ?? null); select(id:string):void{this.store.selectSkill(id)} }
